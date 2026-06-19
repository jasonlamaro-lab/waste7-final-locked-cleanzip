"""
Data Quality Monitor — tracks live price coverage every cycle.

For each market, records:
  - How many constituents returned a valid (non-zero) price
  - Coverage % (valid / total)
  - Whether any TF returns are all-zero (stale price)
  - Timestamp of last valid data

Exposes:
  - record_cycle(market, symbols, price_data) — called from run_equity_cycle
  - get_quality_report() — returns per-market quality snapshot
  - is_data_live(market) — True if coverage ≥ MIN_COVERAGE and last update < MAX_STALE_SECS
  - alert_stale_markets() — returns list of markets that have gone stale
"""
import threading
import time
from datetime import datetime, timezone
from core.logger import logger

# ── Config ───────────────────────────────────────────────────────────────────
MIN_COVERAGE      = 0.50   # at least 50% of constituents must have a valid price
MAX_STALE_SECS    = 300    # data older than 5 minutes = stale (engine runs every 2m)
WARN_COVERAGE     = 0.70   # warn (but don't block) if below 70%

_lock = threading.Lock()
_quality: dict = {}   # market → quality snapshot


def record_cycle(market: str, symbols: list, price_data: dict) -> dict:
    """
    Called once per market per engine cycle.
    symbols: all constituent tickers for this market
    price_data: the batch price dict from the fetcher {sym: {"price": float, ...}}
    Returns quality snapshot for this market.
    """
    total = len(symbols)
    if total == 0:
        return {}

    valid = 0
    stale_syms = []
    missing_syms = []

    for sym in symbols:
        pd = price_data.get(sym)
        if pd is None:
            missing_syms.append(sym)
            continue
        price = pd.get("price", 0)
        if price and price > 0:
            # Also check if all TF returns are zero (stale quote)
            tfs = [pd.get("5m", 0), pd.get("15m", 0), pd.get("30m", 0), pd.get("60m", 0)]
            if all(v == 0.0 for v in tfs):
                stale_syms.append(sym)
            else:
                valid += 1
        else:
            missing_syms.append(sym)

    coverage = valid / total
    now_ts = time.time()
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    snap = {
        "market":        market,
        "total":         total,
        "valid":         valid,
        "stale_prices":  len(stale_syms),
        "missing":       len(missing_syms),
        "coverage_pct":  round(coverage * 100, 1),
        "is_live":       coverage >= MIN_COVERAGE,
        "last_update":   now_str,
        "last_update_ts": now_ts,
        "stale_syms":    stale_syms[:5],    # cap for readability
        "missing_syms":  missing_syms[:5],
    }

    with _lock:
        _quality[market] = snap

    if coverage < MIN_COVERAGE:
        logger.warning("DATA QUALITY %s: only %d/%d valid prices (%.0f%%) — WPS unreliable",
                       market, valid, total, coverage * 100)
    elif coverage < WARN_COVERAGE:
        logger.debug("DATA QUALITY %s: %.0f%% coverage (%d/%d)",
                     market, coverage * 100, valid, total)

    return snap


def is_data_live(market: str) -> bool:
    """True if the market has fresh, sufficient price data.
    On first cycle (no snapshot yet) we allow trading rather than blocking
    indefinitely waiting for a quality record to exist.
    """
    with _lock:
        snap = _quality.get(market)
    if not snap:
        return True  # no data yet — allow through, don't block on startup
    age = time.time() - snap.get("last_update_ts", 0)
    return snap["is_live"] and age < MAX_STALE_SECS


def get_quality_report() -> dict:
    """Full quality snapshot for all markets seen this session."""
    with _lock:
        report = dict(_quality)
    now = time.time()
    for market, snap in report.items():
        age = now - snap.get("last_update_ts", 0)
        snap["age_seconds"] = int(age)
        snap["feed_ok"] = snap["is_live"] and age < MAX_STALE_SECS
    return report


def alert_stale_markets() -> list:
    """Return list of markets where data has gone stale or coverage is too low."""
    report = get_quality_report()
    return [
        {"market": m, "coverage_pct": s["coverage_pct"],
         "age_seconds": s["age_seconds"], "reason": "stale" if s["age_seconds"] >= MAX_STALE_SECS else "low_coverage"}
        for m, s in report.items()
        if not s["feed_ok"]
    ]
