"""EODHD market-data client.

Replaces yfinance for both the per-cycle constituent price feed and the
SL/TS anchor-price fetch in trade_manager.

Single-ticker call:
    GET https://eodhd.com/api/real-time/{TICKER}?api_token=...&fmt=json

Bulk multi-ticker (same exchange):
    GET https://eodhd.com/api/real-time/{HEAD_TICKER}?api_token=...&fmt=json
        &s=TICKER2,TICKER3,...
    (the first ticker is in the path, the rest go in ?s=…)
"""
import logging
import os
import re
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger("trading_platform")

_BASE = "https://eodhd.com/api"
_SESSION = requests.Session()
# Larger connection pool — the batch fetcher hits EODHD from a thread pool.
_ADAPTER = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
_SESSION.mount("https://", _ADAPTER)
_SESSION.mount("http://", _ADAPTER)
_CACHE: Dict[str, Dict] = {}  # ticker → {"price": float, "ts": float}
_CACHE_TTL = 30.0  # seconds


# Per-market index tickers on EODHD. When set, the index price is used as the
# anchor instead of a constituent stock — PnL becomes the real index % move,
# automatically denominated in AUD (because stake is AUD and pct_move is
# dimensionless).
INDEX_TICKERS = {
    "sp500":       "GSPC.INDX",
    "nasdaq100":   "NDX.INDX",
    "dowjones":    "DJI.INDX",
    "dax40":       "GDAXI.INDX",
    "cac40":       "FCHI.INDX",
    "eurostoxx50": "STOXX50E.INDX",
    "aex":         "AEX.INDX",
    "smi":         "SSMI.INDX",
    "ibex35":      "IBEX.INDX",
    "omxs30":      "OMXS30.INDX",
    "nikkei225":   "N225.INDX",
    "hangseng":    "HSI.INDX",
    "csi300":      "HSCE.INDX",   # H-shares proxy (CSI300.INDX is paid-only)
    "asx200":      "AXJO.INDX",
    "kospi":       "KS11.INDX",
    "twse":        "TWII.INDX",
    "sensex":      "BSESN.INDX",
    "tsx":         "GSPTSE.INDX",
    "bovespa":     "BVSP.INDX",
    "set":         "SET.INDX",
    "nzx50":       "NZ50.INDX",
    # No EODHD index ticker available on this tier — falls back to constituent:
    # ftse100, mib, jse, tadawul, ftsemib
}


# Map yfinance suffixes → EODHD exchange codes.
# yfinance gives e.g. "MUFG", "9984.T", "HSBA.L", "BMW.DE", "MC.PA", "PETR4.SA"
# EODHD wants e.g. "MUFG.US", "9984.TSE", "HSBA.LSE", "BMW.XETRA", "MC.PA", "PETR4.SA"
_SUFFIX_MAP = {
    ".L":  ".LSE",
    ".T":  ".TSE",       # Tokyo
    ".HK": ".HK",
    ".DE": ".XETRA",     # Frankfurt XETRA
    ".F":  ".F",         # Frankfurt
    ".PA": ".PA",        # Paris
    ".AS": ".AS",        # Amsterdam
    ".BR": ".BR",        # Brussels
    ".LS": ".LS",        # Lisbon
    ".MI": ".MI",        # Milan
    ".MC": ".MC",        # Madrid
    ".SW": ".SW",        # Swiss SIX
    ".VI": ".VI",        # Vienna
    ".ST": ".ST",        # Stockholm
    ".OL": ".OL",        # Oslo
    ".HE": ".HE",        # Helsinki
    ".CO": ".CO",        # Copenhagen
    ".IR": ".IR",        # Dublin
    ".WA": ".WAR",       # Warsaw
    ".SG": ".SG",        # Stuttgart
    ".AX": ".AU",        # Sydney ASX
    ".NZ": ".NZ",        # New Zealand
    ".SA": ".SA",        # Brazil B3
    ".MX": ".MX",        # Mexico
    ".SR": ".SR",        # Saudi Arabia (Tadawul)
    ".JO": ".JSE",       # Johannesburg
    ".BK": ".BK",        # Thailand SET
    ".KS": ".KO",        # Korea KOSPI
    ".KQ": ".KQ",        # KOSDAQ
    ".TW": ".TW",        # Taiwan
    ".TWO": ".TWO",      # Taiwan OTC
    ".NS": ".NSE",       # India NSE
    ".BO": ".BSE",       # India BSE
    ".TO": ".TO",        # Toronto
    ".V":  ".V",         # TSX Venture
    ".SS": ".SHG",       # Shanghai
    ".SZ": ".SHE",       # Shenzhen
}


def _map_ticker(yf_ticker: str) -> str:
    """Translate a yfinance ticker into the EODHD format."""
    if not yf_ticker:
        return ""
    yf_ticker = yf_ticker.strip().upper()
    # Already EODHD-formatted? (incl. .INDX for indices)
    if re.search(r"\.(US|LSE|TSE|XETRA|AU|NSE|BSE|SHG|SHE|JSE|INDX|HK|TW|TO|F|PA|AS|MI|MC|SW|ST|OL|HE|CO|IR|WAR|SG|NZ|SA|MX|SR|BK|KO|KQ|TWO|V|BR|LS|VI)$", yf_ticker):
        return yf_ticker
    # Multi-letter suffix first (handles ".AX", ".HK", ".SA", ".TWO" etc.)
    for yf_suf in sorted(_SUFFIX_MAP.keys(), key=len, reverse=True):
        if yf_ticker.endswith(yf_suf):
            base = yf_ticker[: -len(yf_suf)]
            return base + _SUFFIX_MAP[yf_suf]
    # No suffix → assume US listing
    return yf_ticker + ".US"


def _token() -> str:
    api_key = os.environ.get("EODHD_API_KEY", "")
    if not api_key:
        logger.warning("EODHD_API_KEY not set — falling back to yfinance only (slower, throttled)")
    return api_key


def get_price(yf_ticker: str) -> float:
    """Return the latest close price for one yfinance-style ticker."""
    if not yf_ticker:
        return 0.0
    eod = _map_ticker(yf_ticker)
    # cache hit?
    now = time.time()
    cached = _CACHE.get(eod)
    if cached and (now - cached["ts"]) < _CACHE_TTL:
        return cached["price"]
    tok = _token()
    if not tok:
        return 0.0
    url = f"{_BASE}/real-time/{eod}"
    try:
        r = _SESSION.get(url, params={"api_token": tok, "fmt": "json"}, timeout=10)
        if r.status_code != 200:
            logger.debug("EODHD price %s HTTP %d %s", eod, r.status_code, r.text[:80])
            return 0.0
        data = r.json()
        price = float(data.get("close") or data.get("previousClose") or 0.0)
        if price > 0:
            _CACHE[eod] = {"price": price, "ts": now}
        return price
    except Exception as exc:
        logger.debug("EODHD price %s error: %s", eod, exc)
        return 0.0


def get_prices_bulk(yf_tickers: List[str]) -> Dict[str, float]:
    """Batched fetch — groups tickers by exchange, one HTTP call per group.

    Returns a dict keyed by the ORIGINAL yfinance ticker string so callers
    don't need to know about the mapping.
    """
    if not yf_tickers:
        return {}
    tok = _token()
    if not tok:
        return {}
    now = time.time()
    out: Dict[str, float] = {}
    pending: Dict[str, List[str]] = {}  # exchange → [eod_ticker, …]
    yf_lookup: Dict[str, str] = {}      # eod_ticker → original yf_ticker

    for yf in yf_tickers:
        eod = _map_ticker(yf)
        if not eod:
            continue
        # cache hit?
        cached = _CACHE.get(eod)
        if cached and (now - cached["ts"]) < _CACHE_TTL:
            out[yf] = cached["price"]
            continue
        # group by exchange suffix
        suf = eod.rsplit(".", 1)[-1] if "." in eod else "US"
        pending.setdefault(suf, []).append(eod)
        yf_lookup[eod] = yf

    for suf, group in pending.items():
        head = group[0]
        rest = group[1:]
        url = f"{_BASE}/real-time/{head}"
        params = {"api_token": tok, "fmt": "json"}
        if rest:
            params["s"] = ",".join(rest)
        try:
            r = _SESSION.get(url, params=params, timeout=15)
            if r.status_code != 200:
                logger.debug("EODHD bulk %s HTTP %d", suf, r.status_code)
                continue
            payload = r.json()
            rows = payload if isinstance(payload, list) else [payload]
            for row in rows:
                code = row.get("code")
                price = float(row.get("close") or row.get("previousClose") or 0.0)
                if not code or price <= 0:
                    continue
                _CACHE[code] = {"price": price, "ts": now}
                yf = yf_lookup.get(code)
                if yf:
                    out[yf] = price
        except Exception as exc:
            logger.debug("EODHD bulk %s error: %s", suf, exc)
            continue
    return out


_INTRADAY_CACHE: Dict[str, Dict] = {}  # eod_ticker → {"data": dict, "ts": float}
_INTRADAY_TTL = 300.0  # seconds — 5-minute bars only refresh every 5 min


def get_intraday_ohlc(yf_ticker: str) -> Optional[Dict[str, float]]:
    """Fetch 5-minute intraday bars and compute the latest price plus the
    multi-timeframe returns (5m/15m/30m/60m) the WPS cycle needs.

    Returns {"price", "5m", "15m", "30m", "60m"} or None on failure. This is
    the EODHD replacement for the old yfinance batch download.
    """
    if not yf_ticker:
        return None
    eod = _map_ticker(yf_ticker)
    now = time.time()
    cached = _INTRADAY_CACHE.get(eod)
    if cached and (now - cached["ts"]) < _INTRADAY_TTL:
        return cached["data"]
    tok = _token()
    if not tok:
        return None
    url = f"{_BASE}/intraday/{eod}"
    try:
        r = _SESSION.get(
            url,
            params={"api_token": tok, "fmt": "json", "interval": "5m"},
            timeout=10,
        )
        if r.status_code != 200:
            logger.debug("EODHD intraday %s HTTP %d", eod, r.status_code)
            return None
        bars = r.json() or []
        if not isinstance(bars, list) or len(bars) < 2:
            return None
        closes = [
            float(b["close"])
            for b in bars
            if isinstance(b, dict) and b.get("close") not in (None, "")
        ]
        if len(closes) < 2:
            return None
        price = closes[-1]
        if price <= 0:
            return None

        def _ret(n: int) -> float:
            if len(closes) < n + 1:
                return 0.0
            old = closes[-(n + 1)]
            return ((price - old) / old) * 100.0 if old else 0.0

        data = {
            "price": price,
            "5m": _ret(1),
            "15m": _ret(3),
            "30m": _ret(6),
            "60m": _ret(12),
        }
        _INTRADAY_CACHE[eod] = {"data": data, "ts": now}
        return data
    except Exception as exc:
        logger.debug("EODHD intraday %s error: %s", eod, exc)
        return None


def get_intraday_5m_return(yf_ticker: str) -> Optional[float]:
    """Return the % move over the last 5-minute interval. Used by the WPS
    cycle to compute direction per constituent."""
    if not yf_ticker:
        return None
    eod = _map_ticker(yf_ticker)
    tok = _token()
    if not tok:
        return None
    url = f"{_BASE}/intraday/{eod}"
    try:
        r = _SESSION.get(
            url,
            params={"api_token": tok, "fmt": "json", "interval": "5m"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        bars = r.json() or []
        if not isinstance(bars, list) or len(bars) < 2:
            return None
        last, prev = bars[-1], bars[-2]
        last_c = float(last.get("close") or 0)
        prev_c = float(prev.get("close") or 0)
        if prev_c <= 0:
            return None
        return ((last_c - prev_c) / prev_c) * 100.0
    except Exception:
        return None
