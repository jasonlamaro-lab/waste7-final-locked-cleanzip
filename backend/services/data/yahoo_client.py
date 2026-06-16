"""Yahoo Finance market-data client.

Free replacement for the EODHD feed. Provides the same public surface the rest
of the platform expects:

    get_price(yf_ticker)              -> float
    get_prices_bulk(yf_tickers)       -> {yf_ticker: price}
    get_intraday_ohlc(yf_ticker)      -> {"price","5m","15m","30m","60m"} | None
    get_intraday_ohlc_batch(symbols)  -> {yf_ticker: {...}}
    get_intraday_5m_return(yf_ticker) -> float | None

Tickers are already in yfinance format throughout the universe (e.g. AAPL,
9984.T, RELIANCE.NS), so no symbol mapping is needed. Returns are expressed as
PERCENTAGES, matching the previous EODHD client contract.
"""
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger("trading_platform")

# Latest close price cache (single-ticker anchor lookups).
_PRICE_CACHE: Dict[str, Dict] = {}      # yf_ticker -> {"price": float, "ts": float}
_PRICE_TTL = 30.0

# Cache intraday bars just under one cycle so every cycle pulls a fresh quote
# (the latest 5-minute bar updates live, so this gives a fresher price each cycle).
_INTRADAY_CACHE: Dict[str, Dict] = {}   # yf_ticker -> {"data": dict, "ts": float}
_INTRADAY_TTL = 55.0


def _yf():
    import yfinance as yf
    return yf


def _clean_closes(values) -> List[float]:
    """Drop NaN/None/non-positive values from a close series."""
    out: List[float] = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f:  # NaN
            continue
        if f > 0:
            out.append(f)
    return out


def _compute(closes: List[float]) -> Optional[Dict[str, float]]:
    """Latest price + multi-timeframe % returns from a list of 5m closes."""
    closes = _clean_closes(closes)
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

    return {
        "price": price,
        "5m": _ret(1),
        "15m": _ret(3),
        "30m": _ret(6),
        "60m": _ret(12),
    }


def get_intraday_ohlc_batch(symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """Fetch 5-minute intraday bars for many tickers in a single Yahoo call.

    Returns {yf_ticker: {"price","5m","15m","30m","60m"}} for every symbol that
    returned usable data. Symbols with no session data today are simply omitted.
    """
    if not symbols:
        return {}

    now = time.time()
    out: Dict[str, Dict[str, float]] = {}
    to_fetch: List[str] = []
    for s in symbols:
        c = _INTRADAY_CACHE.get(s)
        if c and (now - c["ts"]) < _INTRADAY_TTL:
            out[s] = c["data"]
        else:
            to_fetch.append(s)

    if not to_fetch:
        return out

    yf = _yf()
    try:
        df = yf.download(
            tickers=to_fetch,
            period="1d",
            interval="5m",
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False,
        )
    except Exception as exc:
        logger.warning("yahoo batch download failed (%d symbols): %s", len(to_fetch), exc)
        return out

    if df is None or df.empty:
        return out

    # With group_by="ticker", yfinance returns MultiIndex columns (ticker, field)
    # even for a single ticker. Fall back to flat columns just in case.
    multi = getattr(df.columns, "nlevels", 1) > 1
    lvl0 = set(df.columns.get_level_values(0)) if multi else set()
    for s in to_fetch:
        try:
            if multi:
                if s not in lvl0:
                    continue
                sub = df[s]
                if "Close" not in sub.columns:
                    continue
                closes = sub["Close"].tolist()
            else:
                if "Close" not in df.columns:
                    continue
                closes = df["Close"].tolist()
            data = _compute(closes)
            if data:
                _INTRADAY_CACHE[s] = {"data": data, "ts": now}
                out[s] = data
        except Exception as exc:
            logger.debug("yahoo intraday parse %s error: %s", s, exc)
            continue

    return out


def get_intraday_ohlc(yf_ticker: str) -> Optional[Dict[str, float]]:
    """Single-ticker intraday OHLC — thin wrapper over the batch path."""
    if not yf_ticker:
        return None
    return get_intraday_ohlc_batch([yf_ticker]).get(yf_ticker)


def get_intraday_5m_return(yf_ticker: str) -> Optional[float]:
    """% move over the last 5-minute interval, or None."""
    data = get_intraday_ohlc(yf_ticker)
    return data["5m"] if data else None


def get_price(yf_ticker: str) -> float:
    """Latest close price for one yfinance-style ticker."""
    if not yf_ticker:
        return 0.0
    now = time.time()
    cached = _PRICE_CACHE.get(yf_ticker)
    if cached and (now - cached["ts"]) < _PRICE_TTL:
        return cached["price"]

    yf = _yf()
    price = 0.0
    try:
        t = yf.Ticker(yf_ticker)
        try:
            fi = t.fast_info
            price = float(
                getattr(fi, "last_price", None)
                or getattr(fi, "previous_close", None)
                or 0.0
            )
        except Exception:
            price = 0.0
        if price <= 0:
            hist = t.history(period="1d", interval="5m")
            closes = _clean_closes(hist["Close"].tolist()) if not hist.empty else []
            if closes:
                price = closes[-1]
    except Exception as exc:
        logger.debug("yahoo price %s error: %s", yf_ticker, exc)
        return 0.0

    if price > 0:
        _PRICE_CACHE[yf_ticker] = {"price": price, "ts": now}
    return price


def get_prices_bulk(yf_tickers: List[str]) -> Dict[str, float]:
    """Batched latest-price fetch keyed by the original yfinance ticker."""
    data = get_intraday_ohlc_batch(yf_tickers)
    return {k: v["price"] for k, v in data.items() if v.get("price", 0) > 0}
