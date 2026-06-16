"""
Broker Balance Mirror — maintains a persistent TCP connection to cTrader
Open API, fetches the real Pepperstone account balance/equity/margin, and
exposes the latest reading to the rest of the app.

Runs in its own daemon thread with a Twisted reactor. Uses the OAuth tokens
stored in /app/backend/.ctrader_tokens.json. Re-subscribes to trader updates
so balance changes are pushed in real time.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

# CRITICAL: import Twisted reactor here so it's installed before any other
# asyncio reactor hooks. This is required for the ctrader-open-api SDK.
from twisted.internet import ssl, reactor
from twisted.internet.task import LoopingCall

from ctrader_open_api import Client, EndPoints, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAAccountAuthReq,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOATraderReq,
    ProtoOASubscribeSpotsReq,
    ProtoOAReconcileReq,
    ProtoOASymbolsListReq,
    ProtoOASymbolByIdReq,
    ProtoOANewOrderReq,
    ProtoOAAmendPositionSLTPReq,
    ProtoOAClosePositionReq,
    ProtoOAExpectedMarginReq,
    ProtoOAAssetListReq,
    ProtoOAErrorRes,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
    ProtoOAOrderType,
    ProtoOATradeSide,
)
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoHeartbeatEvent

from core.logger import logger

CLIENT_ID = os.environ.get("CTRADER_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("CTRADER_CLIENT_SECRET", "")
ACCOUNT_ID = int(os.environ.get("CTRADER_ACCOUNT_ID", "0") or 0)
TOKEN_FILE = Path(os.environ.get("CTRADER_TOKEN_FILE", str(Path(__file__).resolve().parents[2] / ".ctrader_tokens.json")))

# Live vs Demo host — Pepperstone account 1347709 is LIVE.
# Use live host; fallback handled if auth rejects.
_HOST = EndPoints.PROTOBUF_LIVE_HOST
_PORT = EndPoints.PROTOBUF_PORT

# Shared state, updated by the Twisted thread, read by everyone else.
_state = {
    "connected":         False,
    "account_authorized": False,
    "last_error":        None,
    "last_update":       None,
    # Money metrics (populated once we fetch the trader object)
    "balance":           None,
    "equity":            None,
    "used_margin":       None,
    "free_margin":       None,
    "margin_level":      None,
    "currency":          None,
    # Metadata
    "money_digits":      2,
    "broker_name":       None,
}
_state_lock = threading.Lock()
_started = False

# Symbol id → name (populated once after account auth). Used to translate
# market names like "BTC-USD" into Pepperstone's numeric symbol IDs before
# sending ProtoOANewOrderReq.
_SYMBOL_MAP: Dict[str, int] = {}
# Full symbol details, keyed by broker symbolId (fetched via ProtoOASymbolByIdReq).
# Values: {"name", "digits", "minVolume", "maxVolume", "stepVolume", "lotSize"}
_SYMBOL_DETAILS: Dict[int, dict] = {}
# Pending stop-loss map: trade_id → absolute SL price. Used to fire
# ProtoOAAmendPositionSLTPReq after the market order fills (Pepperstone
# rejects absolute SL on MARKET orders, so we apply it post-fill).
_PENDING_SL: Dict[int, float] = {}
_PENDING_SL_LOCK = threading.Lock()
# Open positions cache, keyed by position_id → {volume, symbolId, side, entry_price, swap, commission}.
# Populated from ProtoOAReconcileRes so we know the volume to pass on close
# and can compute unrealized P&L.
_OPEN_POSITIONS: Dict[int, dict] = {}
_OPEN_POSITIONS_LOCK = threading.Lock()
# Asset list cache: asset_id → "AUD"/"USD"/etc. Fetched once after auth.
_ASSETS: Dict[int, str] = {}
# Margin cache: symbol_id → {"volume": int, "buyMargin": float, "sellMargin": float}
# Populated by ProtoOAExpectedMarginRes. Scales linearly for other volumes.
_MARGIN_CACHE: Dict[int, dict] = {}
_MARGIN_CACHE_LOCK = threading.Lock()
# Pending margin requests: per-symbol Event to unblock the caller once response arrives.
_MARGIN_WAITERS: Dict[int, threading.Event] = {}
_MARGIN_WAITERS_LOCK = threading.Lock()
_MIRROR_INSTANCE = None

# Track the last-sent order so inbound error events can be attributed back
# to the symbol that triggered them (ProtoOAOrderErrorEvent often returns
# orderId=0 when the order was rejected before being accepted).
_LAST_ORDER = {"symbol": None, "ts": 0.0}
_LAST_ORDER_LOCK = threading.Lock()

# Symbol cooldowns: symbol_name → unix ts when the cooldown expires.
# When the broker rejects with NOT_ENOUGH_MONEY / MARKET_CLOSED / etc., we
# park the symbol for a period so we don't keep firing orders that will fail.
_SYMBOL_COOLDOWNS: Dict[str, float] = {}
_COOLDOWN_LOCK = threading.Lock()


def _set_symbol_cooldown(symbol: str, seconds: float, reason: str = ""):
    with _COOLDOWN_LOCK:
        _SYMBOL_COOLDOWNS[symbol] = time.time() + seconds
    logger.info("BalanceMirror: %s parked for %.0fs (%s)", symbol, seconds, reason)


def is_symbol_cooldown(symbol: str) -> bool:
    with _COOLDOWN_LOCK:
        expiry = _SYMBOL_COOLDOWNS.get(symbol, 0)
    return time.time() < expiry


def get_symbol_cooldowns() -> Dict[str, float]:
    """Return symbol → seconds_remaining for live cooldowns."""
    now = time.time()
    with _COOLDOWN_LOCK:
        return {s: max(0.0, e - now) for s, e in _SYMBOL_COOLDOWNS.items() if e > now}


def clear_symbol_cooldown(symbol: str = None):
    """Flush cooldowns — one symbol or all."""
    with _COOLDOWN_LOCK:
        if symbol:
            _SYMBOL_COOLDOWNS.pop(symbol, None)
        else:
            _SYMBOL_COOLDOWNS.clear()


def get_symbol_details_snapshot() -> Dict[str, dict]:
    """Return broker-side symbol details keyed by broker symbol name."""
    out = {}
    for sid, info in _SYMBOL_DETAILS.items():
        name = info.get("name") or str(sid)
        out[name] = info
    return out

# Ring buffer of recent broker events (for UI debugging)
_BROKER_EVENTS: list = []
_BROKER_EVENTS_LOCK = threading.Lock()
_BROKER_EVENTS_MAX = 100


def _record_broker_event(kind: str, data: dict):
    """Push a broker event to the ring buffer (thread-safe)."""
    entry = {
        "kind": kind,
        "ts":   datetime.now(timezone.utc).isoformat(),
        **{k: v for k, v in (data or {}).items()},
    }
    with _BROKER_EVENTS_LOCK:
        _BROKER_EVENTS.append(entry)
        if len(_BROKER_EVENTS) > _BROKER_EVENTS_MAX:
            del _BROKER_EVENTS[:-_BROKER_EVENTS_MAX]


def get_recent_broker_events(limit: int = 50) -> list:
    """Return recent broker events (most recent first)."""
    with _BROKER_EVENTS_LOCK:
        return list(reversed(_BROKER_EVENTS[-limit:]))

# Symbol name aliases: our app name → Pepperstone cTrader symbol name (verified)
_SYMBOL_ALIASES = {
    # Equity indices — verified against Pepperstone's cTrader symbol list
    "asx200":     ["AUS200"],
    "nikkei225":  ["JPN225"],
    "hangseng":   ["HK50"],
    "twse":       ["TWN"],
    "ftse100":    ["UK100"],
    "dax40":      ["GER40"],
    "cac40":      ["FRA40"],
    "eurostoxx50":["EUSTX50"],
    "sp500":      ["US500", "SP500"],
    "nasdaq100":  ["NAS100"],
    "dowjones":   ["US30", "US30m"],
    "nzx50":      ["NZD50"],       # may not be listed
    "csi300":     ["CHINA50", "CN50"],
    "kospi":      ["KOSPI"],
    "sensex":     ["INDIA50", "IN50"],
    "set":        ["TH50"],
    "tadawul":    ["SA"],
    "jse":        ["SAF40", "ZA40"],
    "aex":        ["NETH25"],
    "ibex35":     ["SPA35"],
    "mib":        ["ITA40"],
    "smi":        ["SWISS20", "SMI"],
    "omxs30":     ["SWE30"],
    "bovespa":    ["BRA50"],
    "tsx":        ["CAN60"],
}


# ── Token loader ──────────────────────────────────────────────────────────────
def _load_access_token() -> Optional[str]:
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text())
            return data.get("access_token")
        except Exception:
            return None
    return None


# ── Public read API (called from FastAPI handlers) ────────────────────────────
def get_live_balance_snapshot() -> Dict[str, Any]:
    """Return the latest broker-reported balance state. Safe to call any time."""
    with _state_lock:
        return dict(_state)


# ── Twisted reactor logic ─────────────────────────────────────────────────────
class _BalanceMirror:
    def __init__(self):
        self.client: Optional[Client] = None
        self.access_token: Optional[str] = None

    def start(self):
        self.access_token = _load_access_token()
        if not self.access_token:
            logger.warning("BalanceMirror: no access_token on disk — will retry in 60s")
            reactor.callLater(60, self._retry_start)
            return
        if not CLIENT_ID or not CLIENT_SECRET or not ACCOUNT_ID:
            logger.warning("BalanceMirror: CTRADER_CLIENT_ID / SECRET / ACCOUNT_ID missing")
            return

        self.client = Client(_HOST, _PORT, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message)
        self.client.startService()

    def _retry_start(self):
        self.access_token = _load_access_token()
        if self.access_token:
            self.start()
        else:
            reactor.callLater(60, self._retry_start)

    # ── Connection lifecycle ────────────────────────────────────────────
    def _on_connected(self, client):
        logger.info("BalanceMirror: TCP connected to %s", _HOST)
        with _state_lock:
            _state["connected"] = True
            _state["last_error"] = None
        # Step 1: Application auth
        req = ProtoOAApplicationAuthReq()
        req.clientId = CLIENT_ID
        req.clientSecret = CLIENT_SECRET
        d = client.send(req)
        d.addErrback(self._on_err)

    def _on_disconnected(self, client, reason):
        logger.warning("BalanceMirror: disconnected — %s", reason)
        with _state_lock:
            _state["connected"] = False
            _state["account_authorized"] = False
        # Reconnect in 30s
        reactor.callLater(30, self._reconnect)

    def _reconnect(self):
        try:
            if self.client:
                self.client.startService()
        except Exception as e:
            logger.warning("BalanceMirror reconnect failed: %s", e)
            reactor.callLater(60, self._reconnect)

    # ── Message dispatch ────────────────────────────────────────────────
    def _on_message(self, client, message):
        pt = message.payloadType
        # Log every inbound message's payload type once per session so we can
        # see unknowns. (Heartbeat = 51 is filtered.)
        if pt != 51:
            _seen = getattr(self, "_seen_payload_types", set())
            if pt not in _seen:
                _seen.add(pt)
                self._seen_payload_types = _seen
                logger.info("BalanceMirror: received payloadType=%d (first occurrence)", pt)
        # Application auth OK → fetch account list first to discover cTID trader ID
        if pt == 2101:  # ProtoOAApplicationAuthRes
            logger.info("BalanceMirror: app auth OK — fetching linked accounts")
            req = ProtoOAGetAccountListByAccessTokenReq()
            req.accessToken = self.access_token
            client.send(req)
            return

        # Account auth OK → fetch trader info + start periodic refresh
        if pt == 2103:  # ProtoOAAccountAuthRes
            logger.info("BalanceMirror: account %d authorised", ACCOUNT_ID)
            with _state_lock:
                _state["account_authorized"] = True
            self._fetch_trader()
            self._fetch_positions()
            self._fetch_symbols()
            self._fetch_assets()
            # Refresh every 30s
            LoopingCall(self._fetch_trader).start(30.0, now=False)
            LoopingCall(self._fetch_positions).start(15.0, now=False)
            return

        # Asset list — map asset_id → name/displayName (e.g. 1 → "AUD")
        if pt == 2113:  # ProtoOAAssetListRes
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            try:
                for a in list(decoded.asset):
                    aid = int(getattr(a, "assetId", 0))
                    name = (getattr(a, "displayName", "") or getattr(a, "name", "") or "").strip()
                    if aid and name:
                        _ASSETS[aid] = name
                logger.info("BalanceMirror: cached %d assets (sample=%s)",
                            len(_ASSETS), list(_ASSETS.items())[:8])
                # Refresh trader snapshot so the newly-known currency surfaces
                self._fetch_trader()
            except Exception as e:
                logger.warning("BalanceMirror: asset list parse failed: %s", e)
            return

        # Expected margin response — unblock the pre-flight waiter
        if pt == 2140:  # ProtoOAExpectedMarginRes
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            try:
                md = int(getattr(decoded, "moneyDigits", 2) or 2)
                denom = 10 ** md
                for m in list(decoded.margin):
                    vol = int(getattr(m, "volume", 0) or 0)
                    buy_m = float(getattr(m, "buyMargin", 0) or 0) / denom
                    sell_m = float(getattr(m, "sellMargin", 0) or 0) / denom
                    # Find which symbol this was for via pending waiters — we
                    # keyed requests by symbol_id in place_order, so attribute
                    # to the most recent requested symbol.
                    pass
                # Use the last requested symbol (place_order only fires one at a time)
                with _LAST_ORDER_LOCK:
                    last_sym_name = _LAST_ORDER.get("pending_margin_symbol_id")
                if last_sym_name and list(decoded.margin):
                    m = list(decoded.margin)[0]
                    vol = int(getattr(m, "volume", 0) or 0)
                    buy_m = float(getattr(m, "buyMargin", 0) or 0) / denom
                    sell_m = float(getattr(m, "sellMargin", 0) or 0) / denom
                    with _MARGIN_CACHE_LOCK:
                        _MARGIN_CACHE[int(last_sym_name)] = {
                            "volume": vol, "buyMargin": buy_m, "sellMargin": sell_m,
                            "ts": time.time(),
                        }
                    logger.info("BalanceMirror: margin for symbol %s vol=%d buy=%.2f sell=%.2f",
                                last_sym_name, vol, buy_m, sell_m)
                    with _MARGIN_WAITERS_LOCK:
                        ev = _MARGIN_WAITERS.pop(int(last_sym_name), None)
                    if ev:
                        ev.set()
            except Exception as e:
                logger.warning("BalanceMirror: expected margin parse failed: %s", e)
            return

        # Symbols list (one-time fetch after auth)
        if pt == 2115:  # ProtoOASymbolsListRes
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            try:
                global _SYMBOL_MAP
                syms = list(decoded.symbol)
                _SYMBOL_MAP = {s.symbolName.upper(): s.symbolId for s in syms}
                logger.info("BalanceMirror: %d symbols available from broker", len(_SYMBOL_MAP))
                # Log the symbol names we'll need for trading so user can see they exist
                sample_names = list(_SYMBOL_MAP.keys())[:10]
                logger.info("BalanceMirror: sample symbols: %s", sample_names)
                # Fetch full details (minVolume, digits, lotSize) for the symbols
                # we actually trade so place_order can size correctly.
                self._fetch_symbol_details_for_aliases()
            except Exception as e:
                logger.warning("BalanceMirror: symbols list parse failed: %s", e)
            # Expose the symbol list via a dashboard-visible endpoint
            try:
                from pathlib import Path
                import json
                Path("/tmp/ctrader_symbols.json").write_text(json.dumps(_SYMBOL_MAP))
            except Exception:
                pass
            return

        # Full symbol details (minVolume, digits, lotSize, etc.)
        if pt == 2117:  # ProtoOASymbolByIdRes
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            try:
                for s in list(decoded.symbol):
                    _SYMBOL_DETAILS[int(s.symbolId)] = {
                        "name":        getattr(s, "symbolName", "") or str(s.symbolId),
                        "digits":      int(getattr(s, "digits", 5) or 5),
                        "minVolume":   int(getattr(s, "minVolume", 0) or 0),
                        "maxVolume":   int(getattr(s, "maxVolume", 0) or 0),
                        "stepVolume":  int(getattr(s, "stepVolume", 0) or 0),
                        "lotSize":     int(getattr(s, "lotSize", 0) or 0),
                        "pipPosition": int(getattr(s, "pipPosition", 0) or 0),
                    }
                logger.info("BalanceMirror: cached details for %d symbols (sample=%s)",
                            len(decoded.symbol),
                            [(_SYMBOL_DETAILS[s.symbolId]["name"],
                              _SYMBOL_DETAILS[s.symbolId]["minVolume"],
                              _SYMBOL_DETAILS[s.symbolId]["digits"])
                             for s in list(decoded.symbol)[:5]])
            except Exception as e:
                logger.warning("BalanceMirror: symbol details parse failed: %s", e)
            return

        # Execution event (order fills, rejections, updates)
        if pt == 2126:  # ProtoOAExecutionEvent
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            self._handle_execution_event(decoded)
            return

        # Order error (separate event — fires for rejected orders)
        if pt == 2132:  # ProtoOAOrderErrorEvent
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            try:
                err_code = str(getattr(decoded, "errorCode", "?"))
                desc = getattr(decoded, "description", "")
                order_id = getattr(decoded, "orderId", 0)
                pos_id = getattr(decoded, "positionId", 0)
                logger.error(
                    "BalanceMirror: ORDER REJECTED by broker | errorCode=%s | desc=%s | orderId=%s | positionId=%s",
                    err_code, desc, order_id, pos_id,
                )
                _record_broker_event("ORDER_ERROR", {
                    "errorCode": err_code, "description": desc,
                    "orderId": str(order_id), "positionId": str(pos_id),
                })
                # Attribute to the last-sent symbol (most reliable when orderId=0)
                with _LAST_ORDER_LOCK:
                    last_sym = _LAST_ORDER.get("symbol")
                    last_ts = _LAST_ORDER.get("ts", 0)
                # Apply cooldown rules based on error code
                cooldown_rules = {
                    "NOT_ENOUGH_MONEY":  (3600, "insufficient margin for min volume"),
                    "MARKET_CLOSED":     (300,  "market closed"),
                    "SYMBOL_IS_NOT_FOUND": (86400, "unknown symbol"),
                    "TRADING_DISABLED":  (1800, "trading disabled"),
                    "SYMBOL_HAS_HOLIDAY": (3600, "holiday"),
                    "BAD_VOLUME":        (3600, "volume out of range"),
                }
                if last_sym and (time.time() - last_ts) < 10.0:
                    for code, (secs, reason) in cooldown_rules.items():
                        if code in err_code.upper():
                            _set_symbol_cooldown(last_sym, secs, reason)
                            break
                # Match the most recent pending LIVE trade and mark it REJECTED
                self._mark_pending_rejected(f"{err_code}: {desc}", order_id=order_id)
            except Exception as e:
                logger.warning("BalanceMirror: order error parse failed: %s", e)
            return

        # Reconcile response → open positions (for unrealized P&L)
        if pt == 2125:  # ProtoOAReconcileRes
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            try:
                positions = list(decoded.position)
                # Refresh the OPEN positions cache (used by close_position +
                # unrealized P&L)
                new_cache = {}
                for p in positions:
                    pid = int(getattr(p, "positionId", 0))
                    if pid:
                        trade = p.tradeData if p.HasField("tradeData") else None
                        vol = int(trade.volume) if trade else 0
                        sid = int(trade.symbolId) if trade else 0
                        tside = int(trade.tradeSide) if trade else 0
                        entry_price = float(getattr(p, "price", 0) or 0)
                        swap = float(getattr(p, "swap", 0) or 0) / (10 ** _state.get("money_digits", 2))
                        commission = float(getattr(p, "commission", 0) or 0) / (10 ** _state.get("money_digits", 2))
                        new_cache[pid] = {
                            "volume": vol, "symbolId": sid, "side": tside,
                            "entry_price": entry_price,
                            "swap": swap, "commission": commission,
                        }
                with _OPEN_POSITIONS_LOCK:
                    _OPEN_POSITIONS.clear()
                    _OPEN_POSITIONS.update(new_cache)
                pos_count = len(positions)
                used_margin_total = sum(getattr(p, "usedMargin", 0) for p in positions) / (10 ** _state.get("money_digits", 2))
                unrealized = _compute_unrealized_pnl(new_cache)
                with _state_lock:
                    _state["open_positions"] = pos_count
                    _state["used_margin"] = round(used_margin_total, 2)
                    _state["unrealized_pnl"] = round(unrealized, 2)
                    if _state.get("balance") is not None:
                        _state["equity"] = round(_state["balance"] + unrealized, 2)
                        _state["free_margin"] = round(
                            max(_state["balance"] + unrealized - used_margin_total, 0), 2
                        )
                logger.info("BalanceMirror: %d open position(s), used_margin=%.2f unrealized=%.2f",
                            pos_count, used_margin_total, unrealized)
            except Exception as e:
                logger.warning("BalanceMirror: reconcile parse failed: %s", e)
            return

        # Account list — used to discover the correct cTID trader account ID
        if pt == 2150:  # ProtoOAGetAccountListByAccessTokenRes
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            try:
                accounts = list(decoded.ctidTraderAccount)
                logger.info("BalanceMirror: linked accounts=%s",
                            [(a.ctidTraderAccountId, a.traderLogin, a.isLive) for a in accounts])
                # Pick account that matches the trader login (from env) OR first live account
                env_login = ACCOUNT_ID
                chosen = None
                for a in accounts:
                    if a.traderLogin == env_login:
                        chosen = a; break
                if not chosen:
                    # Prefer live account
                    live = [a for a in accounts if a.isLive]
                    chosen = live[0] if live else (accounts[0] if accounts else None)
                if chosen:
                    actual_id = chosen.ctidTraderAccountId
                    logger.info("BalanceMirror: authorising ctidTraderAccountId=%d (login=%d, live=%s)",
                                actual_id, chosen.traderLogin, chosen.isLive)
                    self._account_id_resolved = actual_id
                    req = ProtoOAAccountAuthReq()
                    req.ctidTraderAccountId = actual_id
                    req.accessToken = self.access_token
                    client.send(req)
            except Exception as e:
                logger.warning("BalanceMirror: account list parse failed: %s", e)
            return

        # Trader data arrived
        if pt == 2122:  # ProtoOATraderRes
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            try:
                trader = decoded.trader
                self._update_state_from_trader(trader)
            except Exception as e:
                logger.warning("BalanceMirror: trader parse failed: %s", e)
            return

        # Trader update event (pushed when balance changes)
        if pt == 2123:  # ProtoOATraderUpdatedEvent
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            try:
                self._update_state_from_trader(decoded.trader)
            except Exception as e:
                logger.warning("BalanceMirror: trader update parse failed: %s", e)
            return

        # Errors
        if pt == 2142 or pt == 50:
            from ctrader_open_api import Protobuf
            decoded = Protobuf.extract(message)
            err = getattr(decoded, "errorCode", "?")
            desc = getattr(decoded, "description", "")
            logger.error("BalanceMirror: error %s — %s", err, desc)
            _record_broker_event("ERROR", {"errorCode": str(err), "description": desc})
            with _state_lock:
                _state["last_error"] = f"{err}: {desc}"
            return

        # Unknown / unhandled payloads — log once so we can see the stream
        if pt not in (51,):
            _unhandled = getattr(self, "_unhandled_payload_types", set())
            if pt not in _unhandled:
                _unhandled.add(pt)
                self._unhandled_payload_types = _unhandled
                logger.info("BalanceMirror: UNHANDLED payloadType=%d (will not log again)", pt)

    # ── Execution event → DB reconciliation ────────────────────────────
    def _handle_execution_event(self, decoded):
        """Parse ProtoOAExecutionEvent and update the local `trades` row."""
        try:
            ev_type = int(getattr(decoded, "executionType", 0))
            order = getattr(decoded, "order", None)
            position = getattr(decoded, "position", None)
            deal = getattr(decoded, "deal", None)
            err_code = getattr(decoded, "errorCode", "") or ""

            # ExecutionType enum (from cTrader):
            #   1 ORDER_ACCEPTED
            #   2 ORDER_FILLED
            #   3 ORDER_REPLACED
            #   4 ORDER_CANCELLED
            #   5 ORDER_EXPIRED
            #   6 ORDER_REJECTED
            #   7 ORDER_CANCEL_REJECTED
            #   8 SWAP
            #   9 DEPOSIT_WITHDRAW
            ev_names = {1: "ACCEPTED", 2: "FILLED", 3: "REPLACED", 4: "CANCELLED",
                        5: "EXPIRED", 6: "REJECTED", 7: "CANCEL_REJECTED",
                        8: "SWAP", 9: "DEPOSIT_WITHDRAW"}
            ev_name = ev_names.get(ev_type, f"TYPE_{ev_type}")

            # Extract identifiers
            order_id = str(getattr(order, "orderId", 0)) if order else "0"
            pos_id = str(getattr(position, "positionId", 0)) if position else "0"
            label = ""
            if order and hasattr(order, "tradeData"):
                label = getattr(order.tradeData, "label", "") or ""
            if (not label) and position and hasattr(position, "tradeData"):
                label = getattr(position.tradeData, "label", "") or ""
            fill_price = 0.0
            if deal:
                fill_price = float(getattr(deal, "executionPrice", 0) or 0)
            if fill_price == 0.0 and position and hasattr(position, "price"):
                fill_price = float(getattr(position, "price", 0) or 0)

            logger.info(
                "BalanceMirror: EXEC_EVENT %s | orderId=%s posId=%s label=%s fill=%.4f err=%s",
                ev_name, order_id, pos_id, label, fill_price, err_code,
            )
            _record_broker_event("EXEC_" + ev_name, {
                "orderId": order_id, "positionId": pos_id, "label": label,
                "fillPrice": fill_price, "errorCode": str(err_code),
            })

            # Map back to our local DB trade_id via the label ("tid-123")
            trade_id = None
            if label.startswith("tid-"):
                try:
                    trade_id = int(label.split("-", 1)[1])
                except Exception:
                    trade_id = None

            from core.db import db_cursor
            if ev_type == 2:  # FILLED
                if trade_id:
                    with db_cursor() as (conn, cur):
                        cur.execute(
                            "UPDATE trades SET status='OPEN', broker_status='FILLED', "
                            "broker_order_id=?, broker_position_id=?, "
                            "broker_fill_price=COALESCE(NULLIF(?,0), broker_fill_price), "
                            "entry_price=COALESCE(NULLIF(?,0), entry_price) "
                            "WHERE id=? AND is_sim=0",
                            (order_id, pos_id, fill_price, fill_price, trade_id),
                        )
                        logger.info("BalanceMirror: trade %d marked FILLED (pos=%s @ %.4f)",
                                    trade_id, pos_id, fill_price)
                    # Attach the stashed SL via ProtoOAAmendPositionSLTPReq
                    with _PENDING_SL_LOCK:
                        sl_price = _PENDING_SL.pop(int(trade_id), None)
                    if sl_price and pos_id != "0":
                        self._amend_position_sltp(int(pos_id), sl_price)
                else:
                    logger.warning("BalanceMirror: FILLED event with no label (orderId=%s)", order_id)
            elif ev_type == 3:  # REPLACED — carries the actual fill price
                if trade_id and fill_price > 0:
                    with db_cursor() as (conn, cur):
                        cur.execute(
                            "UPDATE trades SET broker_fill_price=?, entry_price=? "
                            "WHERE id=? AND is_sim=0",
                            (fill_price, fill_price, trade_id),
                        )
                    logger.info("BalanceMirror: trade %d fill price updated to %.4f",
                                trade_id, fill_price)
            elif ev_type in (4, 5, 6, 7):  # CANCELLED / EXPIRED / REJECTED
                reason = f"{ev_name}:{err_code}"
                if trade_id:
                    self._cancel_trade_in_db(trade_id, reason)
                else:
                    self._mark_pending_rejected(reason, order_id=int(order_id or 0))

            # Pull fresh positions + balance regardless of event type
            reactor.callLater(1, self._fetch_positions)
            reactor.callLater(2, self._fetch_trader)
        except Exception as e:
            logger.warning("BalanceMirror: execution event handler failed: %s", e)

    def _cancel_trade_in_db(self, trade_id: int, reason: str):
        try:
            from core.db import db_cursor
            from services.intelligence.kitty_manager import release as kitty_release
        except Exception:
            kitty_release = None
        try:
            with db_cursor() as (conn, cur):
                cur.execute(
                    "SELECT symbol, size, kitty_level, status FROM trades WHERE id=?",
                    (trade_id,),
                )
                row = cur.fetchone()
                if not row:
                    return
                symbol, size, level, status = row
                if status in ("CLOSED", "REJECTED"):
                    return
                cur.execute(
                    "UPDATE trades SET status='REJECTED', broker_status='REJECTED', "
                    "broker_error=?, closed_at=CURRENT_TIMESTAMP WHERE id=?",
                    (reason, trade_id),
                )
                logger.error("BalanceMirror: trade %d REJECTED — %s", trade_id, reason)
            if kitty_release:
                try:
                    kitty_release(symbol or "", float(size or 0))
                except Exception:
                    pass
        except Exception as e:
            logger.warning("BalanceMirror: cancel_trade_in_db failed: %s", e)

    def _mark_pending_rejected(self, reason: str, order_id: int = 0):
        """Fallback when we can't match by label — kill the most recent
        PENDING LIVE trade (any symbol) so it doesn't sit forever."""
        try:
            from core.db import db_cursor
            with db_cursor() as (conn, cur):
                cur.execute(
                    "SELECT id FROM trades WHERE is_sim=0 AND broker_status='PENDING' "
                    "ORDER BY id DESC LIMIT 1"
                )
                r = cur.fetchone()
            if r:
                self._cancel_trade_in_db(int(r[0]), reason)
        except Exception as e:
            logger.warning("BalanceMirror: mark_pending_rejected failed: %s", e)

    def _fetch_trader(self):
        if not self.client:
            return
        acc_id = getattr(self, "_account_id_resolved", ACCOUNT_ID)
        req = ProtoOATraderReq()
        req.ctidTraderAccountId = acc_id
        self.client.send(req)

    def _fetch_positions(self):
        """Pull open positions so we can compute used_margin + free_margin."""
        if not self.client:
            return
        acc_id = getattr(self, "_account_id_resolved", ACCOUNT_ID)
        req = ProtoOAReconcileReq()
        req.ctidTraderAccountId = acc_id
        self.client.send(req)

    def _fetch_symbols(self):
        if not self.client:
            return
        acc_id = getattr(self, "_account_id_resolved", ACCOUNT_ID)
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = acc_id
        self.client.send(req)

    def _fetch_assets(self):
        if not self.client:
            return
        acc_id = getattr(self, "_account_id_resolved", ACCOUNT_ID)
        req = ProtoOAAssetListReq()
        req.ctidTraderAccountId = acc_id
        self.client.send(req)

    def _fetch_expected_margin(self, symbol_id: int, volume: int):
        if not self.client:
            return
        acc_id = getattr(self, "_account_id_resolved", ACCOUNT_ID)
        req = ProtoOAExpectedMarginReq()
        req.ctidTraderAccountId = acc_id
        req.symbolId = int(symbol_id)
        req.volume.append(int(volume))
        # Remember which symbol this request was for so the async response
        # can be attributed back to the right waiter.
        with _LAST_ORDER_LOCK:
            _LAST_ORDER["pending_margin_symbol_id"] = int(symbol_id)
        self.client.send(req)

    def _check_affordability(self, symbol_id: int, volume: int, side: str) -> tuple:
        """Reactor-side: only read the cache. The caller (`send_live_order`)
        is responsible for populating it before scheduling place_order."""
        return _check_affordability_cached(symbol_id, volume, side)

    def _amend_position_sltp(self, position_id: int, sl_price: float):
        """Attach SL to an already-open position (post-fill).
        Pepperstone requires this for market orders — absolute SL on the
        initial ProtoOANewOrderReq is rejected."""
        if not self.client or position_id <= 0 or sl_price <= 0:
            return
        acc_id = getattr(self, "_account_id_resolved", ACCOUNT_ID)
        req = ProtoOAAmendPositionSLTPReq()
        req.ctidTraderAccountId = acc_id
        req.positionId = position_id
        req.stopLoss = float(sl_price)
        self.client.send(req)
        logger.info("BalanceMirror: attaching SL=%.5f to position %d", sl_price, position_id)
        _record_broker_event("AMEND_SL", {"positionId": str(position_id), "sl": sl_price})

    def close_position(self, position_id: int, volume: int = 0) -> dict:
        """Send ProtoOAClosePositionReq to fully (or partially) close a position.
        volume=0 → close the full position (we look up the broker-reported
        volume from the reconcile cache)."""
        if not self.client:
            return {"ok": False, "error": "broker client not ready"}
        if position_id <= 0:
            return {"ok": False, "error": "invalid position_id"}
        # Resolve volume from the most recent reconcile if caller didn't pass one
        if volume <= 0:
            with _OPEN_POSITIONS_LOCK:
                cached = _OPEN_POSITIONS.get(int(position_id), {})
            volume = int(cached.get("volume", 0) or 0)
        if volume <= 0:
            return {"ok": False, "error": f"no cached volume for position {position_id} — run reconcile first"}
        acc_id = getattr(self, "_account_id_resolved", ACCOUNT_ID)
        req = ProtoOAClosePositionReq()
        req.ctidTraderAccountId = acc_id
        req.positionId = int(position_id)
        req.volume = int(volume)
        self.client.send(req)
        logger.info("BalanceMirror: close position %d (volume=%d)", position_id, volume)
        _record_broker_event("CLOSE_SENT", {
            "positionId": str(position_id), "volume": volume,
        })
        return {"ok": True, "volume": volume}

    def _fetch_symbol_details_for_aliases(self):
        """Pull full ProtoOASymbol details (minVolume, digits, lotSize) for
        every broker symbol id that's in our alias table. Cached results are
        used by place_order to size volume + round SL price correctly."""
        if not self.client or not _SYMBOL_MAP:
            return
        acc_id = getattr(self, "_account_id_resolved", ACCOUNT_ID)
        wanted_ids = set()
        for _, aliases in _SYMBOL_ALIASES.items():
            for alias in aliases:
                sid = _SYMBOL_MAP.get(alias.upper())
                if sid:
                    wanted_ids.add(sid)
                    break
        if not wanted_ids:
            return
        # cTrader accepts a batch request
        req = ProtoOASymbolByIdReq()
        req.ctidTraderAccountId = acc_id
        for sid in wanted_ids:
            req.symbolId.append(sid)
        self.client.send(req)
        logger.info("BalanceMirror: requested details for %d symbols", len(wanted_ids))

    def place_order(self, symbol_name: str, side: str, volume: int,
                    stop_loss_price: float = 0.0, trade_id: int = 0) -> dict:
        """
        Place a market order on the authenticated broker connection.
        symbol_name: one of our app names (e.g. 'BTC-USD', 'asx200')
        side: 'BUY' or 'SELL'
        volume: in cTrader units (1/100 of a lot)
        stop_loss_price: absolute SL price, 0 = no SL
        trade_id: our local trades.id — round-tripped via label field so we
                  can match the ExecutionEvent back to the DB row.
        """
        if not self.client:
            return {"ok": False, "error": "broker client not ready"}
        if not _SYMBOL_MAP:
            return {"ok": False, "error": "symbol list not loaded yet"}

        # Resolve our name → broker symbol id
        aliases = _SYMBOL_ALIASES.get(symbol_name, [symbol_name.replace("-", "").replace("_", "").upper()])
        broker_name = None
        symbol_id = None
        for alias in aliases:
            if alias.upper() in _SYMBOL_MAP:
                broker_name = alias.upper()
                symbol_id = _SYMBOL_MAP[broker_name]
                break
        if symbol_id is None:
            return {"ok": False, "error": f"no broker symbol for {symbol_name} (tried {aliases})"}

        # Apply per-symbol details (minVolume / stepVolume / digits)
        details = _SYMBOL_DETAILS.get(symbol_id) or {}
        min_vol = int(details.get("minVolume", 0) or 0)
        step_vol = int(details.get("stepVolume", 0) or 0)
        digits = int(details.get("digits", 5) or 5)
        final_volume = int(volume)
        if min_vol and final_volume < min_vol:
            logger.info("BalanceMirror: volume %d < minVolume %d for %s — scaling up",
                        final_volume, min_vol, broker_name)
            final_volume = min_vol
        if step_vol and step_vol > 1:
            # Snap to nearest multiple of stepVolume
            final_volume = max(min_vol or step_vol,
                               (final_volume // step_vol) * step_vol)

        # Round SL to the symbol's allowed digits
        rounded_sl = round(float(stop_loss_price), digits) if stop_loss_price > 0 else 0.0

        # Pre-flight margin check (uses data already cached — populated by
        # send_live_order BEFORE it schedules place_order on the reactor
        # thread, so this is a non-blocking lookup here).
        affordable, est_margin = _check_affordability_cached(symbol_id, final_volume, side)
        free_margin = (_state.get("free_margin") or _state.get("balance") or 0) * 0.9
        if not affordable:
            logger.error("BalanceMirror: PRE-FLIGHT REJECT %s vol=%d — estimated margin=%.2f > free*0.9=%.2f",
                         symbol_name, final_volume, est_margin, free_margin)
            _record_broker_event("PREFLIGHT_REJECT", {
                "symbol": symbol_name, "volume": final_volume,
                "est_margin": round(est_margin, 2), "free_margin": round(free_margin, 2),
            })
            _set_symbol_cooldown(symbol_name, 86400, "insufficient free margin (pre-flight)")
            return {"ok": False, "error": f"insufficient free margin: need {est_margin:.2f}, have {free_margin:.2f}"}

        acc_id = getattr(self, "_account_id_resolved", ACCOUNT_ID)
        req = ProtoOANewOrderReq()
        req.ctidTraderAccountId = acc_id
        req.symbolId = symbol_id
        req.orderType = ProtoOAOrderType.MARKET
        req.tradeSide = ProtoOATradeSide.BUY if side.upper() == "BUY" else ProtoOATradeSide.SELL
        req.volume = final_volume
        # Pepperstone rejects absolute stopLoss on MARKET orders
        # ("SL/TP in absolute values are allowed only for LIMIT/STOP/STOP_LIMIT").
        # Stash the SL and apply it via ProtoOAAmendPositionSLTPReq once we
        # receive the ExecutionEvent with the positionId.
        if rounded_sl > 0 and trade_id:
            with _PENDING_SL_LOCK:
                _PENDING_SL[int(trade_id)] = rounded_sl
        req.comment = "auto-trader"
        if trade_id:
            req.label = f"tid-{trade_id}"
        # Record the last-sent symbol so error events (orderId=0) can be
        # attributed back to the correct symbol for cooldown tracking.
        with _LAST_ORDER_LOCK:
            _LAST_ORDER["symbol"] = symbol_name
            _LAST_ORDER["ts"] = time.time()
        self.client.send(req)
        logger.info("PLACED ORDER: %s %s id=%d (broker=%s) vol=%d (min=%d digits=%d) SL=%.5f label=%s",
                    side, symbol_name, symbol_id, broker_name, final_volume,
                    min_vol, digits, rounded_sl, getattr(req, "label", ""))
        _record_broker_event("ORDER_SENT", {
            "symbol": symbol_name, "broker_name": broker_name,
            "side": side, "volume": final_volume, "sl": rounded_sl,
            "label": getattr(req, "label", ""),
        })
        return {"ok": True, "symbol_id": symbol_id, "broker_name": broker_name,
                "volume": final_volume, "min_volume": min_vol, "digits": digits}

    def _update_state_from_trader(self, trader):
        money_digits = getattr(trader, "moneyDigits", 2) or 2
        denom = 10 ** money_digits
        balance   = getattr(trader, "balance", 0) / denom
        # Decode depositAssetId → "AUD"/"USD"/etc from the cached asset list
        asset_id  = getattr(trader, "depositAssetId", None)
        currency  = _ASSETS.get(int(asset_id), str(asset_id)) if asset_id else "USD"
        broker    = getattr(trader, "brokerName", "Pepperstone")
        with _state_lock:
            _state["balance"]           = round(balance, 2)
            # Recompute equity from balance + current unrealized (set by reconcile)
            unrealized = _state.get("unrealized_pnl", 0) or 0
            _state["equity"]            = round(balance + unrealized, 2)
            # Don't zero out used_margin / free_margin here — those are
            # owned by the reconcile handler (trader updates don't carry
            # margin data).
            used_m = _state.get("used_margin", 0) or 0
            _state["free_margin"]       = round(max(balance + unrealized - used_m, 0), 2)
            _state["currency"]          = str(currency)
            _state["broker_name"]       = str(broker)
            _state["money_digits"]      = int(money_digits)
            _state["last_update"]       = datetime.now(timezone.utc).isoformat()
            _state["last_error"]        = None
        logger.info("BalanceMirror: balance=%.2f %s (account %d)",
                    balance, currency, ACCOUNT_ID)

    def _on_err(self, failure):
        logger.warning("BalanceMirror: send error — %s", failure)
        with _state_lock:
            _state["last_error"] = str(failure)


# ── Public startup (called once from FastAPI lifespan) ────────────────────────
def start_in_background():
    """Kick off Twisted reactor in a daemon thread.
    Safe to call multiple times — idempotent."""
    global _started, _MIRROR_INSTANCE
    if _started:
        return
    _started = True

    def _run():
        global _MIRROR_INSTANCE
        try:
            mirror = _BalanceMirror()
            _MIRROR_INSTANCE = mirror
            # Give the rest of the app 5s to finish bootstrapping before we
            # open the broker socket.
            reactor.callLater(5, mirror.start)
            reactor.run(installSignalHandlers=False)
        except Exception as e:
            logger.exception("BalanceMirror thread crashed: %s", e)

    threading.Thread(target=_run, daemon=True, name="ctrader-balance-mirror").start()
    logger.info("BalanceMirror: background thread started")


def _compute_unrealized_pnl(positions_cache: dict) -> float:
    """Equity-only platform: we don't track unrealized P&L on broker positions
    here (yfinance is async and equity CFDs aren't typically used). Returns 0."""
    return 0.0


def _check_affordability_cached(symbol_id: int, volume: int, side: str) -> tuple:
    """Read the margin cache and return (affordable, estimated_margin).
    Reactor-safe — pure cache read, no blocking."""
    free_margin = (_state.get("free_margin")
                   if _state.get("free_margin") is not None
                   else _state.get("balance"))
    if free_margin is None:
        return True, 0.0  # unknown balance → allow
    budget = float(free_margin) * 0.9
    with _MARGIN_CACHE_LOCK:
        cached = _MARGIN_CACHE.get(int(symbol_id))
    if not cached or (time.time() - cached.get("ts", 0)) > 300:
        return True, 0.0  # no data → allow, broker will enforce
    ref_vol = max(cached.get("volume", 1), 1)
    key = "buyMargin" if side.upper() == "BUY" else "sellMargin"
    per_unit = cached.get(key, 0) / ref_vol
    est = per_unit * volume
    return (est <= budget), est


def _ensure_margin_cache(symbol_id: int, volume: int, wait_seconds: float = 1.5):
    """Caller-side (NOT reactor): if margin cache is stale, fire a margin
    request via the reactor and block the caller thread briefly for the
    response. Must NOT be called from the reactor thread."""
    with _MARGIN_CACHE_LOCK:
        cached = _MARGIN_CACHE.get(int(symbol_id))
    if cached and (time.time() - cached.get("ts", 0)) <= 300:
        return  # fresh
    if _MIRROR_INSTANCE is None:
        return
    ev = threading.Event()
    with _MARGIN_WAITERS_LOCK:
        _MARGIN_WAITERS[int(symbol_id)] = ev
    from twisted.internet import reactor as _r
    _r.callFromThread(_MIRROR_INSTANCE._fetch_expected_margin, int(symbol_id), int(volume))
    ev.wait(timeout=wait_seconds)


def send_live_order(symbol_name: str, side: str, volume: int,
                    stop_loss_price: float = 0.0, trade_id: int = 0) -> dict:
    """Public entry point — called from pepperstone_broker.place_real_order.
    Safe to call from any thread; schedules the send inside the Twisted reactor."""
    if _MIRROR_INSTANCE is None:
        return {"ok": False, "error": "mirror not started"}
    snap = get_live_balance_snapshot()
    if not snap.get("account_authorized"):
        return {"ok": False, "error": "broker not authorised"}

    # Pre-flight margin cache: ensure we have fresh broker-quoted margin data
    # for this symbol BEFORE we hand off to the reactor. This runs on the
    # caller thread so it's safe to block briefly waiting for the response.
    try:
        # Resolve symbol_id for the margin request
        aliases = _SYMBOL_ALIASES.get(symbol_name, [symbol_name.replace("-", "").replace("_", "").upper()])
        sid = None
        for alias in aliases:
            sid = _SYMBOL_MAP.get(alias.upper())
            if sid:
                break
        if sid:
            _ensure_margin_cache(sid, max(volume, 1), wait_seconds=1.5)
    except Exception as e:
        logger.warning("send_live_order: margin pre-fetch failed: %s", e)

    # Schedule the send onto the Twisted reactor thread (ProtoOA.send must
    # happen on the reactor, not the caller's thread).
    from twisted.internet import reactor as _r
    result_holder = {"result": None}
    event = threading.Event()

    def _do_send():
        try:
            result_holder["result"] = _MIRROR_INSTANCE.place_order(
                symbol_name, side, volume, stop_loss_price, trade_id=trade_id)
        except Exception as e:
            result_holder["result"] = {"ok": False, "error": str(e)}
        finally:
            event.set()

    _r.callFromThread(_do_send)
    event.wait(timeout=5.0)
    return result_holder["result"] or {"ok": False, "error": "order send timeout"}


def close_live_position(position_id: int, volume: int = 0) -> dict:
    """Public entry point — close a real Pepperstone position. Thread-safe."""
    if _MIRROR_INSTANCE is None:
        return {"ok": False, "error": "mirror not started"}
    snap = get_live_balance_snapshot()
    if not snap.get("account_authorized"):
        return {"ok": False, "error": "broker not authorised"}
    from twisted.internet import reactor as _r
    result_holder = {"result": None}
    event = threading.Event()

    def _do_close():
        try:
            result_holder["result"] = _MIRROR_INSTANCE.close_position(position_id, volume)
        except Exception as e:
            result_holder["result"] = {"ok": False, "error": str(e)}
        finally:
            event.set()

    _r.callFromThread(_do_close)
    event.wait(timeout=5.0)
    return result_holder["result"] or {"ok": False, "error": "close send timeout"}
