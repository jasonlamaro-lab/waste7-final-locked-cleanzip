"""
System cycle — runs ALL 25 equity markets per cycle using a single batched
yfinance download. Crypto engines removed (equity-only platform).
"""
import json
import os
import threading
import time
from core.config import SYSTEM_CYCLE_SECONDS, TRADE_UPDATE_INTERVAL
from core.data_sources import fetch_all_equity_batch
from core.logger import logger
from core.pipeline import maybe_execute_trade
from core.state import STATE
from engines.equity.market_engine import MarketEngine
from services.execution.trade_manager import update_open_trades
from core.db import db_cursor

RUNNING_LOCK = threading.Lock()

_OFFSET_FILE = os.path.join(os.path.dirname(__file__), "..", "cycle_offset.json")
_OFFSET_FILE = os.path.normpath(_OFFSET_FILE)


def _read_offset() -> dict:
    try:
        with open(_OFFSET_FILE) as f:
            return json.load(f)
    except Exception:
        return {"cycle_count": 0}


def _write_offset(data: dict):
    try:
        with open(_OFFSET_FILE, "w") as f:
            json.dump(data, f)
    except Exception as exc:
        logger.warning("Could not write cycle_offset.json: %s", exc)


_ALL_EQUITY_SLUGS = [
    "nasdaq100", "sp500", "dowjones",
    "asx200", "nzx50",
    "ftse100", "dax40", "cac40", "eurostoxx50", "aex", "ibex35", "mib", "omxs30", "smi",
    "nikkei225", "hangseng", "csi300", "kospi", "sensex", "twse", "set",
    "tsx", "bovespa",
    "tadawul", "jse",
]

EQUITY_ENGINE_MAP: dict[str, MarketEngine] = {}
for _slug in _ALL_EQUITY_SLUGS:
    try:
        EQUITY_ENGINE_MAP[_slug] = MarketEngine(_slug)
    except Exception as _exc:
        logger.warning("Failed to load market engine %s: %s", _slug, _exc)

_MASTER_SYMBOLS: list[str] = []
_seen: set[str] = set()
for _slug in _ALL_EQUITY_SLUGS:
    eng = EQUITY_ENGINE_MAP.get(_slug)
    if eng:
        for sym in eng.weights.keys():
            if sym not in _seen:
                _MASTER_SYMBOLS.append(sym)
                _seen.add(sym)

logger.info("Master symbol list: %d unique symbols across %d markets", len(_MASTER_SYMBOLS), len(EQUITY_ENGINE_MAP))


def _persist_signal(market: str, result: dict):
    try:
        with db_cursor() as (conn, cursor):
            cursor.execute("""
                INSERT INTO signals (market, symbol, signal, confidence, wps, alignment, regime)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                market,
                market,
                result.get("signal"),
                result.get("confidence"),
                result.get("wps"),
                result.get("alignment"),
                result.get("regime"),
            ))
    except Exception as exc:
        logger.warning("_persist_signal failed for %s: %s", market, exc)


def run_equity_cycle(price_data: dict) -> dict:
    market_results = {}
    for slug in _ALL_EQUITY_SLUGS:
        engine = EQUITY_ENGINE_MAP.get(slug)
        if not engine:
            continue
        try:
            symbols = list(engine.weights.keys())
            market_prices = {sym: price_data[sym] for sym in symbols if sym in price_data}

            # Record data quality for this market every cycle
            try:
                from services.data.quality_monitor import record_cycle, is_data_live
                dq = record_cycle(engine.market_name, symbols, price_data)
                data_live = dq.get("is_live", True)
            except Exception:
                data_live = True

            if not market_prices or not data_live:
                STATE["markets"][engine.market_name] = {
                    "signal": None,
                    "wps": 0,
                    "alignment": 0,
                    "regime": "CLOSED",
                    "confidence": 0,
                    "timeframes": [],
                    "stale": True,
                    "reason": "market closed / no data" if not market_prices else "data quality too low",
                    "data_quality": dq if 'dq' in dir() else {},
                }
                continue
            result = engine.run(market_prices)
            result["stale"] = False
            result["data_quality"] = dq if 'dq' in dir() else {}
            # Dashboard live ticker price: use the same canonical anchor if possible.
            _CANONICAL_ANCHORS = {
                    "nikkei225":  "9984.T",
                    "eurostoxx50":"ASML.AS",
                    "ftse100":    "HSBA.L",
                    "bovespa":    "PETR4.SA",
                    "twse":       "2330.TW",
                    "hangseng":   "0700.HK",
                    "csi300":     "600519.SS",
                    "tsx":        "RY.TO",
                    "sp500":      "AAPL",
                    "nasdaq100":  "MSFT",
                    "dax40":      "SAP.DE",
                    "cac40":      "MC.PA",
                    "asx200":     "BHP.AX",
                    "kospi":      "005930.KS",
                    "sensex":     "RELIANCE.NS",
                    "omxs30":     "VOLV-B.ST",
                    "ibex35":     "SAN.MC",
                    "smi":        "NESN.SW",
                    "aex":        "ASML.AS",
                }
            try:
                _anchor = _CANONICAL_ANCHORS.get(engine.market_name)
                _p = market_prices.get(_anchor, {}).get("price", 0) if _anchor else 0
                if not _p:
                    for _sym in engine.weights.keys():
                        _p = market_prices.get(_sym, {}).get("price", 0)
                        if _p:
                            break
                if _p:
                    result["price"] = round(float(_p), 4)
            except Exception:
                pass
            STATE["markets"][engine.market_name] = result
            market_results[engine.market_name] = result
            _persist_signal(engine.market_name, result)

            if result.get("signal"):
                # Anchor selection — use the canonical per-market constituent
                # (user-supplied pip-conversion dataset). pnl_aud math is then:
                #   pnl_aud = stake_aud × (current_anchor − entry_anchor) / entry_anchor
                _CANONICAL_ANCHORS = {
                    "nikkei225":  "9984.T",
                    "eurostoxx50":"ASML.AS",
                    "ftse100":    "HSBA.L",
                    "bovespa":    "PETR4.SA",
                    "twse":       "2330.TW",
                    "hangseng":   "0700.HK",
                    "csi300":     "600519.SS",
                    "tsx":        "RY.TO",
                    "sp500":      "AAPL",
                    "nasdaq100":  "MSFT",
                    "dax40":      "SAP.DE",
                    "cac40":      "MC.PA",
                    "asx200":     "BHP.AX",
                    "kospi":      "005930.KS",
                    "sensex":     "RELIANCE.NS",
                    "omxs30":     "VOLV-B.ST",
                    "ibex35":     "SAN.MC",
                    "smi":        "NESN.SW",
                    "aex":        "ASML.AS",
                }
                price = 0
                anchor_sym = _CANONICAL_ANCHORS.get(engine.market_name)
                if anchor_sym:
                    # 1) try the cycle's batch fetch
                    p = market_prices.get(anchor_sym, {}).get("price", 0)
                    if p <= 0:
                        # 2) live Yahoo Finance lookup
                        try:
                            from services.data.yahoo_client import get_price
                            p = get_price(anchor_sym) or 0
                        except Exception:
                            pass
                    if p > 0:
                        price = p
                    else:
                        anchor_sym = None  # fall through to constituent picker
                if not anchor_sym:
                    # Fallback: first constituent with a valid price
                    for sym in engine.weights.keys():
                        p = market_prices.get(sym, {}).get("price", 0)
                        if p > 0:
                            price = p
                            anchor_sym = sym
                            break
                if price <= 0:
                    logger.info("%s signal %s generated but no valid anchor price — skipping",
                                engine.market_name, result.get("signal"))
                    continue
                trade = maybe_execute_trade(
                    engine="equity",
                    symbol=engine.market_name,
                    side=result["signal"],
                    price=price,
                    reason=f"{result['regime']} | WPS {result['wps']:.2f}",
                    wps=float(result.get("wps") or 0),
                    regime=str(result.get("regime") or "NEUTRAL"),
                    anchor_symbol=anchor_sym,
                    timeframes={tf["tf"]: (1 if tf.get("dir") == "BUY" else -1 if tf.get("dir") == "SELL" else 0)
                                for tf in result.get("timeframes", [])},
                    confidence=float(result.get("confidence") or 0),
                    alignment=int(result.get("alignment") or 0),
                )
                if trade:
                    logger.info("Equity trade created for %s", engine.market_name)
        except Exception as exc:
            logger.warning("run_equity_cycle: error for %s — %s", slug, exc)

    STATE["engines"]["equity"] = {
        "status": "RUNNING" if market_results else "DEGRADED",
        "markets_updated": len(market_results),
    }
    return market_results


def run_system_cycle():
    if not RUNNING_LOCK.acquire(blocking=False):
        logger.info("Cycle already running — skipping")
        return
    try:
        offset = _read_offset()
        cycle_count = offset.get("cycle_count", 0)
        t_start = time.time()
        logger.info("System cycle #%d starting — %d markets, 1 batch fetch", cycle_count, len(EQUITY_ENGINE_MAP))

        try:
            update_open_trades()
        except Exception as exc:
            logger.warning("update_open_trades failed: %s", exc)

        t_fetch = time.time()
        price_data = fetch_all_equity_batch(_MASTER_SYMBOLS)
        logger.info("Batch fetch complete: %d symbols in %.1fs", len(price_data), time.time() - t_fetch)

        market_results = run_equity_cycle(price_data)
        logger.info("Equity cycle complete: %d/%d markets updated", len(market_results), len(EQUITY_ENGINE_MAP))

        STATE["last_cycle"] = time.time()
        elapsed = time.time() - t_start
        logger.info("System cycle #%d complete in %.1fs", cycle_count, elapsed)
        _write_offset({"cycle_count": cycle_count + 1})
    except Exception as exc:
        logger.exception("System cycle failed: %s", exc)
        STATE["status"] = "DEGRADED"
    finally:
        RUNNING_LOCK.release()


def trade_update_loop():
    logger.info("Trade update loop started (interval=%ds)", TRADE_UPDATE_INTERVAL)
    while True:
        try:
            update_open_trades()
        except Exception as exc:
            logger.warning("trade_update_loop error: %s", exc)
        time.sleep(TRADE_UPDATE_INTERVAL)


def start_loop():
    logger.info("Background system loop started")
    trade_thread = threading.Thread(target=trade_update_loop, daemon=True)
    trade_thread.start()
    while True:
        run_system_cycle()
        time.sleep(SYSTEM_CYCLE_SECONDS)
