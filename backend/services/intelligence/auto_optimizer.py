"""
Auto-Optimizer — reviews recent trade history and tunes gate tightness + per-market
behaviour to keep the platform performing at its best without manual intervention.

Runs automatically after every completed engine cycle (called from engine_runner).

Logic:
  - Per market: sample the last WINDOW trades. If win_rate < TARGET, loosen that
    market's WPS gate (let more signals through to learn faster). If win_rate ≥ TARGET
    AND trade count ≥ MIN_SAMPLE, tighten slightly to filter noise.
  - Global gates: if overall system win_rate < TARGET over last WINDOW, reduce gate
    tightness across all 6 gates by STEP. Never below 0.0.
  - If overall win_rate ≥ TARGET, inch gates up by STEP. Never above MAX_TIGHTNESS.
  - Skips markets with < MIN_SAMPLE closed trades (not enough data).
  - All changes logged to system_events for auditability.

This is conservative by design: STEP is small, changes are bounded, and the
optimizer never brainwashes or resets markets (that's the tuner's job).
"""
import json
from core.db import db_cursor
from core.logger import logger

# ── Config ──────────────────────────────────────────────────────────────────
TARGET_WIN_RATE   = 0.52   # aim for just above breakeven (fees ~2%)
WINDOW            = 20     # trades to sample per market
MIN_SAMPLE        = 5      # don't adjust until we have at least this many
STEP              = 0.05   # gate tightness change per optimizer run
MAX_TIGHTNESS     = 0.40   # never tighten past here (keep gates permissive)
# NOTE: WPS gate tightness up to 1.0 is valid (effective threshold up to 100).
# MAX_TIGHTNESS applies to general gate nudging.

# WPS gate auto-range: how many |WPS| points to raise/lower per run
WPS_STEP          = 2.0
WPS_FLOOR         = 10.0
WPS_CEILING       = 90.0   # raised: live markets regularly hit 70-100; old 30 cap was blocking valid signals
WPS_DEFAULT       = 72.0   # aligned with platform standard threshold


def _system_win_rate(window: int) -> tuple[float, int]:
    """Overall win rate across all markets for last `window` closed trades."""
    with db_cursor() as (_, cur):
        cur.execute("""
            SELECT pnl FROM trades
            WHERE status = 'CLOSED'
            ORDER BY id DESC LIMIT ?
        """, (window,))
        rows = cur.fetchall()
    if not rows:
        return 0.0, 0
    wins = sum(1 for r in rows if (r[0] or 0) > 0)
    return wins / len(rows), len(rows)


def _market_win_rate(market: str, window: int) -> tuple[float, int]:
    with db_cursor() as (_, cur):
        cur.execute("""
            SELECT pnl FROM trades
            WHERE symbol = ? AND status = 'CLOSED'
            ORDER BY id DESC LIMIT ?
        """, (market, window))
        rows = cur.fetchall()
    if not rows:
        return 0.0, 0
    wins = sum(1 for r in rows if (r[0] or 0) > 0)
    return wins / len(rows), len(rows)


def _get_market_wps_threshold(market: str) -> float:
    with db_cursor() as (_, cur):
        cur.execute("SELECT config FROM market_state WHERE market = ?", (market,))
        row = cur.fetchone()
        if row and row[0]:
            try:
                return float(json.loads(row[0]).get("wps_threshold", WPS_DEFAULT))
            except Exception:
                pass
    return WPS_DEFAULT


def _get_market_config(market: str) -> dict:
    with db_cursor() as (_, cur):
        cur.execute("SELECT config FROM market_state WHERE market = ?", (market,))
        row = cur.fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0]) or {}
        except Exception:
            return {}
    return {}


def _manual_override(cfg: dict, *keys: str) -> bool:
    """Manual dashboard settings have priority over automation.
    If any matching manual flag is true, the auto systems must not change it.
    """
    return any(bool(cfg.get(k)) for k in keys)


def _set_market_wps_threshold(market: str, new_val: float) -> None:
    new_val = round(max(WPS_FLOOR, min(WPS_CEILING, new_val)), 1)
    with db_cursor() as (_, cur):
        cur.execute("SELECT config FROM market_state WHERE market = ?", (market,))
        row = cur.fetchone()
        d: dict = {}
        if row and row[0]:
            try:
                d = json.loads(row[0])
            except Exception:
                d = {}
        d["wps_threshold"] = new_val
        cur.execute(
            "UPDATE market_state SET config = ?, updated_at = CURRENT_TIMESTAMP WHERE market = ?",
            (json.dumps(d), market),
        )


def _nudge_market_gates(market: str, delta: float) -> list[str]:
    """Nudge all tunable gate tightness values for a specific market by delta."""
    from core.gates import load_settings, save_market_gate_settings
    # Never auto-move TIME4/alignment; Jason controls that globally from the dashboard.
    tunable = ["TRENDING", "WPS", "CONF", "RISK"]
    settings = load_settings(market)
    cfg = _get_market_config(market)
    overrides: dict = {}
    changed = []
    for gate in tunable:
        if gate == "WPS" and _manual_override(cfg, "manual_wps_override", "manual_gate_WPS"):
            continue
        if gate == "CONF" and _manual_override(cfg, "manual_conf_override", "manual_gate_CONF"):
            continue
        current = settings["gates"].get(gate, {}).get("tightness", 0.0)
        new_val = round(max(0.0, min(MAX_TIGHTNESS, current + delta)), 3)
        if new_val != current:
            overrides[gate] = {"tightness": new_val}
            changed.append(f"{gate}:{current:.2f}→{new_val:.2f}")
    if overrides:
        save_market_gate_settings(market, overrides)
    return changed


def _log_event(msg: str) -> None:
    with db_cursor() as (_, cur):
        cur.execute(
            "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
            ("INFO", "auto_optimizer", msg),
        )


def _suppress_market(market: str) -> bool:
    """Return True if market should be skipped this cycle (rolling loss suppressor).
    A market is suppressed if its last 5 trades are ALL losses. The suppress flag
    is temporary — clears on next win. This is softer than brainwash."""
    with db_cursor() as (_, cur):
        cur.execute("""
            SELECT pnl FROM trades
            WHERE symbol = ? AND status = 'CLOSED'
            ORDER BY id DESC LIMIT 5
        """, (market,))
        rows = cur.fetchall()
    if len(rows) < 5:
        return False
    return all((r[0] or 0) <= 0 for r in rows)


def is_market_suppressed(market: str) -> bool:
    """Public — called from pipeline to skip signal if market is in backoff."""
    return _suppress_market(market)


def run_optimizer() -> dict:
    """
    Entry point — called once per engine cycle.
    Returns a summary dict of what was adjusted.
    """
    from core.gates import load_settings, _save_settings

    changes = {"markets": [], "gates": []}

    # ── 1. Per-market WPS threshold ──────────────────────────────────────────
    with db_cursor() as (_, cur):
        cur.execute("SELECT market FROM market_state")
        markets = [r[0] for r in cur.fetchall()]

    for market in markets:
        wr, count = _market_win_rate(market, WINDOW)
        if count < MIN_SAMPLE:
            continue
        cfg = _get_market_config(market)
        if _manual_override(cfg, "manual_wps_override"):
            continue
        old = _get_market_wps_threshold(market)
        if wr < TARGET_WIN_RATE:
            # Losing — raise the bar, only take stronger signals
            new = old + WPS_STEP
            direction = "tightened"
        else:
            # Winning — hold or inch down slightly to keep signal flow healthy
            new = old - (WPS_STEP * 0.5)
            direction = "loosened"
        new = round(max(WPS_FLOOR, min(WPS_CEILING, new)), 1)
        if new != old:
            _set_market_wps_threshold(market, new)
            msg = f"{market}: WPS {direction} {old}→{new} (wr={wr:.0%} n={count})"
            _log_event(msg)
            changes["markets"].append(msg)
            logger.debug("AutoOpt: %s", msg)

    # ── 2. Per-market gate tightness ─────────────────────────────────────────
    # Each market gets its own gate settings tuned by its own win rate.
    for market in markets:
        wr, count = _market_win_rate(market, WINDOW)
        if count < MIN_SAMPLE:
            continue
        if wr < TARGET_WIN_RATE:
            # Losing — tighten gates, demand better setups
            nudged = _nudge_market_gates(market, +STEP)
            direction = "tightened"
        else:
            # Winning — ease back slightly to keep trade flow healthy
            nudged = _nudge_market_gates(market, -(STEP * 0.5))
            direction = "loosened"
        if nudged:
            msg = f"{market}: gates {direction} [{', '.join(nudged)}] (wr={wr:.0%} n={count})"
            _log_event(msg)
            changes["gates"].append(msg)
            logger.debug("AutoOpt: %s", msg)

    return changes
