"""IG Markets REST API client (DEMO + LIVE).

Session-token flow:
  1. POST /session with API key + identifier + password
  2. Capture CST + X-SECURITY-TOKEN from response headers
  3. Send those headers (plus X-IG-API-KEY) on every subsequent call
"""
import logging
import os
import threading
import time
from typing import Optional

import requests

logger = logging.getLogger("trading_platform")

_state = {
    "cst": None,
    "x_security_token": None,
    "account_id": None,
    "account_balance": None,
    "currency": None,
    "connected": False,
    "last_login_at": 0,
    "last_error": None,
}
_lock = threading.Lock()


def _base_url() -> str:
    return os.environ.get("IG_BASE_URL", "https://demo-api.ig.com/gateway/deal").rstrip("/")


def _headers(version: str = "2", include_session: bool = True) -> dict:
    h = {
        "X-IG-API-KEY": os.environ.get("IG_API_KEY", ""),
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json; charset=UTF-8",
        "Version": version,
    }
    if include_session:
        if _state["cst"]:
            h["CST"] = _state["cst"]
        if _state["x_security_token"]:
            h["X-SECURITY-TOKEN"] = _state["x_security_token"]
    return h


def connect() -> dict:
    """POST /session to authenticate and capture session tokens."""
    api_key  = os.environ.get("IG_API_KEY")
    user     = os.environ.get("IG_USERNAME")
    password = os.environ.get("IG_PASSWORD")
    if not (api_key and user and password):
        _state["last_error"] = "Missing IG_API_KEY / IG_USERNAME / IG_PASSWORD in env"
        return {"connected": False, "error": _state["last_error"]}

    url = f"{_base_url()}/session"
    payload = {"identifier": user, "password": password}
    try:
        r = requests.post(url, json=payload, headers=_headers(version="2", include_session=False), timeout=20)
    except Exception as exc:
        _state["last_error"] = f"Network error: {exc}"
        _state["connected"] = False
        logger.warning("IG connect network error: %s", exc)
        return {"connected": False, "error": _state["last_error"]}

    if r.status_code != 200:
        _state["last_error"] = f"HTTP {r.status_code}: {r.text[:200]}"
        _state["connected"] = False
        logger.warning("IG connect failed: %s", _state["last_error"])
        return {"connected": False, "error": _state["last_error"], "status": r.status_code}

    with _lock:
        _state["cst"] = r.headers.get("CST")
        _state["x_security_token"] = r.headers.get("X-SECURITY-TOKEN")
        body = r.json() if r.content else {}
        _state["account_id"]      = body.get("currentAccountId")
        _state["currency"]        = body.get("currencyIsoCode") or body.get("currencySymbol")
        _state["account_balance"] = (body.get("accountInfo") or {}).get("balance")
        _state["connected"]       = bool(_state["cst"] and _state["x_security_token"])
        _state["last_login_at"]   = time.time()
        _state["last_error"]      = None

    logger.info("IG connected | acct=%s currency=%s balance=%s",
                _state["account_id"], _state["currency"], _state["account_balance"])
    return {
        "connected": _state["connected"],
        "account_id": _state["account_id"],
        "currency": _state["currency"],
        "balance": _state["account_balance"],
    }


def get_status() -> dict:
    return {
        "connected": bool(_state["connected"]),
        "account_id": _state["account_id"],
        "currency": _state["currency"],
        "balance": _state["account_balance"],
        "account_type": os.environ.get("IG_ACCOUNT_TYPE", "DEMO"),
        "last_error": _state["last_error"],
        "last_login_at": _state["last_login_at"],
    }


def fetch_accounts() -> Optional[dict]:
    """GET /accounts — health check that the session is still valid."""
    if not _state["connected"]:
        return None
    url = f"{_base_url()}/accounts"
    try:
        r = requests.get(url, headers=_headers(version="1"), timeout=15)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (401, 403):
            # session expired — invalidate
            with _lock:
                _state["connected"] = False
                _state["last_error"] = "Session expired"
        return {"status": r.status_code, "body": r.text[:200]}
    except Exception as exc:
        _state["last_error"] = f"accounts error: {exc}"
        return None


def fetch_positions() -> Optional[list]:
    if not _state["connected"]:
        return None
    url = f"{_base_url()}/positions"
    try:
        r = requests.get(url, headers=_headers(version="2"), timeout=15)
        if r.status_code == 200:
            return (r.json() or {}).get("positions", [])
        if r.status_code in (401, 403):
            with _lock:
                _state["connected"] = False
        return None
    except Exception as exc:
        logger.warning("IG fetch_positions error: %s", exc)
        return None


def place_market_order(epic: str, direction: str, size: float,
                       stop_distance: Optional[float] = None,
                       trailing_distance: Optional[float] = None,
                       currency: str = "AUD") -> dict:
    """POST /positions/otc — open a market position with optional SL/TS."""
    if not _state["connected"]:
        return {"ok": False, "error": "not connected"}
    url = f"{_base_url()}/positions/otc"
    body = {
        "epic": epic,
        "expiry": "-",
        "direction": direction.upper(),  # BUY | SELL
        "size": size,
        "orderType": "MARKET",
        "guaranteedStop": False,
        "forceOpen": True,
        "currencyCode": currency,
    }
    if stop_distance is not None:
        body["stopDistance"] = float(stop_distance)
    if trailing_distance is not None:
        body["trailingStop"] = True
        body["trailingStopDistance"] = float(trailing_distance)
        body["trailingStopIncrement"] = max(1.0, float(trailing_distance) / 10)
    try:
        r = requests.post(url, json=body, headers=_headers(version="2"), timeout=20)
        if r.status_code == 200:
            return {"ok": True, "deal_reference": (r.json() or {}).get("dealReference")}
        return {"ok": False, "status": r.status_code, "error": r.text[:300]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def close_position(deal_id: str, direction: str, size: float) -> dict:
    if not _state["connected"]:
        return {"ok": False, "error": "not connected"}
    url = f"{_base_url()}/positions/otc"
    body = {
        "dealId": deal_id,
        "direction": "SELL" if direction.upper() == "BUY" else "BUY",
        "size": size,
        "orderType": "MARKET",
    }
    headers = _headers(version="1")
    headers["_method"] = "DELETE"  # IG uses _method override
    try:
        r = requests.post(url, json=body, headers=headers, timeout=20)
        if r.status_code == 200:
            return {"ok": True, "deal_reference": (r.json() or {}).get("dealReference")}
        return {"ok": False, "status": r.status_code, "error": r.text[:300]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Market → IG epic mapping ──────────────────────────────────────────────────
# Demo-tradable IG epics for our equity indices. Anything not in the map will
# stay on SIM (no IG order is placed).
IG_EPIC_MAP = {
    # All epics verified on IG demo as TRADEABLE / A$1-per-point contracts.
    # Smallest exposure available for AUD accounts.
    "sp500":       {"epic": "IX.D.SPTRD.IFA.IP",     "min_size": 1.0, "min_stop_pts": 30},
    "nasdaq100":   {"epic": "IX.D.NASDAQ.IFA.IP",    "min_size": 1.0, "min_stop_pts": 80},
    "dowjones":    {"epic": "IX.D.DOW.IFA.IP",       "min_size": 1.0, "min_stop_pts": 60},
    "ftse100":     {"epic": "IX.D.FTSE.IFA.IP",      "min_size": 1.0, "min_stop_pts": 20},
    "dax40":       {"epic": "IX.D.DAX.IFA.IP",       "min_size": 1.0, "min_stop_pts": 50},
    "cac40":       {"epic": "IX.D.CAC.IFA.IP",       "min_size": 1.0, "min_stop_pts": 20},
    "eurostoxx50": {"epic": "IX.D.STXE.IFA.IP",      "min_size": 1.0, "min_stop_pts": 15},
    "aex":         {"epic": "IX.D.AEX.IFA.IP",       "min_size": 1.0, "min_stop_pts": 15},
    "smi":         {"epic": "IX.D.SMI.IFA.IP",       "min_size": 1.0, "min_stop_pts": 20},
    "ibex35":      {"epic": "IX.D.IBEX.IFA.IP",      "min_size": 1.0, "min_stop_pts": 20},
    "omxs30":      {"epic": "IX.D.OMX.IFA.IP",       "min_size": 1.0, "min_stop_pts": 15},
    "nikkei225":   {"epic": "IX.D.NIKKEI.IFA.IP",    "min_size": 1.0, "min_stop_pts": 60},
    "hangseng":    {"epic": "IX.D.HANGSENG.IFA.IP",  "min_size": 1.0, "min_stop_pts": 40},
    "csi300":      {"epic": "IX.D.XINHUA.IFA.IP",    "min_size": 1.0, "min_stop_pts": 30},
    "jse":         {"epic": "IX.D.SAF.IFA.IP",       "min_size": 1.0, "min_stop_pts": 40},
    "asx200":      {"epic": "IX.D.ASX.IFT.IP",       "min_size": 1.0, "min_stop_pts": 20},
}


def submit_market_order(market_key: str, side: str, stake_aud: float,
                        sl_pct: float = 7.0, ts_pct: float = 6.5) -> dict:
    """Convert our internal market+stake into an IG market order.

    stake_aud is the AUD risk per trade. We use the smallest contract size for
    the instrument (typically 0.5–1.0 IG points-per-trade). SL is computed
    from `min_stop_pts` so it's always far enough from current price that IG
    accepts the order. The trailing distance defaults to ~85% of the SL.
    """
    info = IG_EPIC_MAP.get(market_key)
    if not info:
        return {"ok": False, "error": f"no IG epic mapping for {market_key}"}

    size = info["min_size"]
    sl_points = float(info["min_stop_pts"])
    ts_points = max(sl_points * 0.85, info["min_stop_pts"] / 2)

    direction = side.upper()
    if direction not in ("BUY", "SELL"):
        return {"ok": False, "error": f"invalid side {side}"}

    return place_market_order(
        epic=info["epic"],
        direction=direction,
        size=size,
        stop_distance=sl_points,
        trailing_distance=ts_points,
        currency="AUD",
    )
