"""
Monthly refresh of equity constituents. For each market, pulls the current
market cap of each ticker in its universe, then keeps the top-N whose
cumulative weight >= PIVOT_THRESHOLD (80%).

Stored in the DB table `market_constituents` and read by MarketEngine on load.
"""
import json
import time
from typing import Dict, List, Tuple
from datetime import datetime

try:
    import yfinance as yf
except Exception:
    yf = None

from core.db import db_cursor
from core.logger import logger
from engines.equity.universe import UNIVERSE, PIVOT_THRESHOLD


def _ensure_table():
    with db_cursor() as (_, cursor):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_constituents (
                market      TEXT PRIMARY KEY,
                data        TEXT NOT NULL,
                refreshed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)


def _fetch_market_cap(ticker: str) -> float:
    """Fetch market cap for a single ticker. Returns 0.0 on failure."""
    if yf is None:
        return 0.0
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        cap = info.get("marketCap") or info.get("sharesOutstanding", 0) * info.get("regularMarketPrice", 0)
        return float(cap or 0)
    except Exception:
        return 0.0


def refresh_market(slug: str) -> Dict:
    """Refresh constituent weights for a single market. Returns summary dict."""
    entry = UNIVERSE.get(slug)
    if not entry:
        return {"ok": False, "error": f"no universe for {slug}"}

    tickers = entry["tickers"]
    sectors = entry.get("sectors", {})
    caps: List[Tuple[str, float]] = []

    for tk in tickers:
        cap = _fetch_market_cap(tk)
        if cap > 0:
            caps.append((tk, cap))
        time.sleep(0.05)  # be gentle on yfinance

    if not caps:
        return {"ok": False, "error": f"no market cap data for {slug}"}

    caps.sort(key=lambda x: x[1], reverse=True)
    total = sum(c for _, c in caps)

    # Walk descending until cumulative weight >= pivot
    selected = []
    cumulative = 0.0
    for tk, cap in caps:
        w = cap / total
        selected.append((tk, cap, w))
        cumulative += w
        if cumulative >= PIVOT_THRESHOLD:
            break

    # Re-normalise selected so weights sum to 1.0
    selected_total = sum(c for _, c, _ in selected)
    constituents = {
        tk: {"weight": round(cap / selected_total, 4), "sector": sectors.get(tk, "misc")}
        for tk, cap, _ in selected
    }

    payload = {
        "constituents": constituents,
        "pivot_threshold": PIVOT_THRESHOLD,
        "universe_size": len(tickers),
        "selected_count": len(selected),
        "total_market_cap": total,
        "refreshed_at": datetime.utcnow().isoformat(),
    }

    _ensure_table()
    with db_cursor() as (_, cursor):
        cursor.execute("""
            INSERT INTO market_constituents (market, data, refreshed_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(market) DO UPDATE SET
                data = excluded.data,
                refreshed_at = CURRENT_TIMESTAMP
        """, (slug, json.dumps(payload)))

    logger.info("Constituents refreshed: %s — %d/%d tickers, cumulative=%.1f%%",
                slug, len(selected), len(tickers), cumulative * 100)
    return {"ok": True, "market": slug, "selected": len(selected),
            "from_universe": len(tickers), "cumulative_pct": round(cumulative * 100, 1)}


def refresh_all(priority_only: bool = False) -> List[Dict]:
    """Refresh all markets. If priority_only, refresh in exchange-open order,
    stopping at priority-5."""
    order = sorted(UNIVERSE.keys(), key=lambda k: UNIVERSE[k].get("opens_utc_hour", 99))
    if priority_only:
        order = order[:5]
    results = []
    for slug in order:
        r = refresh_market(slug)
        results.append(r)
    return results


def get_constituents(slug: str) -> Dict:
    """Read the latest refreshed constituents for a market. Falls back to the
    hardcoded MARKET_DEFINITIONS when no refresh has happened yet."""
    _ensure_table()
    with db_cursor() as (_, cursor):
        cursor.execute("SELECT data, refreshed_at FROM market_constituents WHERE market = ?", (slug,))
        row = cursor.fetchone()
        if row and row[0]:
            try:
                data = json.loads(row[0])
                data["refreshed_at"] = row[1]
                return data
            except Exception:
                pass
    # Fallback — read the static MARKET_DEFINITIONS
    try:
        from engines.equity.markets import MARKET_DEFINITIONS
        defn = MARKET_DEFINITIONS.get(slug, {})
        return {
            "constituents": defn.get("constituents", {}),
            "refreshed_at": None,
            "source": "static_fallback",
        }
    except Exception:
        return {"constituents": {}, "refreshed_at": None}


def status() -> List[Dict]:
    """Return refresh status for every market."""
    _ensure_table()
    out = []
    with db_cursor() as (_, cursor):
        cursor.execute("SELECT market, refreshed_at FROM market_constituents")
        refreshed = {r[0]: r[1] for r in cursor.fetchall()}
    for slug, cfg in UNIVERSE.items():
        out.append({
            "market":       slug,
            "universe":     len(cfg["tickers"]),
            "opens_utc":    cfg.get("opens_utc_hour"),
            "refreshed_at": refreshed.get(slug),
        })
    out.sort(key=lambda x: (x["opens_utc"] if x["opens_utc"] is not None else 99))
    return out
