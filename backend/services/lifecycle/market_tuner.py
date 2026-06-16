"""
Market Tuner — trade-management safety only.

FINAL AUTHORITY SPLIT:
  - Manual dashboard override: highest authority.
  - Auto-Optimizer: owns strategy gates/thresholds (WPS, CONF, TRENDING, RISK).
  - Market Tuner: owns trade management only (stop loss, trailing stop, TS activation, cooldown/SIM safety).
  - Mode-A: retired/removed. It must not adjust WPS.

Jason's operating theory:
  - The platform is meant to pick market direction.
  - If a trade goes against the selected direction immediately, it is probably wrong.
  - Therefore a tight stop loss is acceptable. Current preferred working SL is around 0.8%.
  - The tuner should cut bad trades quickly but must not keep tightening the trailing stop so much that it trims normal profit movement.

This module is intentionally conservative:
  - It NEVER changes WPS.
  - It NEVER changes CONF.
  - It NEVER changes alignment/TIME4.
  - It logs every automatic change to system_events.
"""
import json
from statistics import mean
from typing import Dict, Any, List

from core.db import db_cursor
from core.logger import logger

DEFAULTS = {
    # Tight default. Jason has been running around 0.8 and wants wrong-direction trades cut fast.
    "stop_loss_pct": 0.8,
    # Trailing starts tight enough to protect profit, but not below 0.6 unless manually set.
    "trailing_stop_pct": 0.8,
    # Trail only arms once the trade is positive enough to cover noise/fees.
    "ts_activation_pct": 0.8,
    # Tuner cooldown is written for visibility; entry cooldown still uses the trade-close path.
    "cooldown_minutes": 3,
}

CONSECUTIVE_LOSSES_TO_TUNE = 5
REVIEW_WINDOW = 20
MIN_FLOOR_SL = 0.4
MAX_SL = 2.0
MIN_TRAIL = 0.6
MAX_TRAIL = 3.0
MIN_TS_ACTIVATION = 0.6
MAX_TS_ACTIVATION = 3.0
STEP = 0.10  # 10% tune step. Small enough to avoid yanking settings around.


def _default_config(_: str) -> Dict[str, float]:
    return dict(DEFAULTS)


def _get_config(market: str) -> Dict[str, float]:
    base = _default_config(market)
    with db_cursor() as (_, cursor):
        cursor.execute("SELECT config FROM market_state WHERE market = ?", (market,))
        row = cursor.fetchone()
    if row and row[0]:
        try:
            cfg = {**base, **(json.loads(row[0]) or {})}
        except Exception:
            cfg = base
    else:
        cfg = base

    # Guard rails. Manual overrides can still set values inside these broad safety bands.
    cfg["stop_loss_pct"] = round(max(MIN_FLOOR_SL, min(MAX_SL, float(cfg.get("stop_loss_pct", DEFAULTS["stop_loss_pct"])))), 2)
    cfg["trailing_stop_pct"] = round(max(MIN_TRAIL, min(MAX_TRAIL, float(cfg.get("trailing_stop_pct", DEFAULTS["trailing_stop_pct"])))), 2)
    cfg["ts_activation_pct"] = round(max(MIN_TS_ACTIVATION, min(MAX_TS_ACTIVATION, float(cfg.get("ts_activation_pct", DEFAULTS["ts_activation_pct"])))), 2)
    cfg["cooldown_minutes"] = int(max(0, min(120, int(cfg.get("cooldown_minutes", DEFAULTS["cooldown_minutes"])))))
    return cfg


def _save_config(market: str, cfg: Dict[str, float]) -> None:
    with db_cursor() as (_, cursor):
        cursor.execute(
            "UPDATE market_state SET config = ?, updated_at = CURRENT_TIMESTAMP WHERE market = ?",
            (json.dumps(cfg), market),
        )


def _recent_closes(market: str, limit: int = REVIEW_WINDOW) -> List[dict]:
    with db_cursor() as (_, cursor):
        cursor.execute(
            """
            SELECT id, pnl, pnl_pct, size, reason, created_at, closed_at
            FROM trades
            WHERE symbol = ? AND status = 'CLOSED'
            ORDER BY id DESC LIMIT ?
            """,
            (market, limit),
        )
        rows = cursor.fetchall()
    return [
        {
            "id": r[0],
            "pnl": float(r[1] or 0.0),
            "pnl_pct": float(r[2] or r[1] or 0.0),
            "size": float(r[3] or 0.0),
            "reason": r[4] or "",
            "created_at": r[5],
            "closed_at": r[6],
        }
        for r in rows
    ]


def _is_losing(trade: dict) -> bool:
    return float(trade.get("pnl") or 0.0) < 0


def _consecutive_losses(market: str, window: int = CONSECUTIVE_LOSSES_TO_TUNE) -> int:
    streak = 0
    for t in _recent_closes(market, window * 2):
        if _is_losing(t):
            streak += 1
        else:
            break
    return streak


def _metrics(market: str) -> Dict[str, Any]:
    rows = _recent_closes(market, REVIEW_WINDOW)
    wins = [r["pnl"] for r in rows if r["pnl"] > 0]
    losses = [abs(r["pnl"]) for r in rows if r["pnl"] < 0]
    ts_wins = [r["pnl"] for r in rows if r["pnl"] > 0 and "TS_HIT" in r["reason"]]
    sl_losses = [abs(r["pnl"]) for r in rows if r["pnl"] < 0 and "SL_HIT" in r["reason"]]
    gross_win = sum(wins)
    gross_loss = sum(losses)
    return {
        "count": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(rows)) if rows else 0.0,
        "avg_win": mean(wins) if wins else 0.0,
        "avg_loss": mean(losses) if losses else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        "ts_win_count": len(ts_wins),
        "avg_ts_win": mean(ts_wins) if ts_wins else 0.0,
        "sl_loss_count": len(sl_losses),
        "avg_sl_loss": mean(sl_losses) if sl_losses else 0.0,
    }


def _manual_risk_override(cfg: dict) -> bool:
    return bool(cfg.get("manual_risk_override") or cfg.get("manual_sl_override") or cfg.get("manual_trailing_override"))


def _apply_tune(cfg: Dict[str, float], m: Dict[str, Any]) -> tuple[Dict[str, float], list[str]]:
    """Tune trade management only. Never changes WPS/CONF/gate thresholds."""
    new = dict(cfg)
    changes: list[str] = []

    if _manual_risk_override(cfg):
        return new, ["manual risk override active; tuner held SL/TS"]

    sl = float(cfg.get("stop_loss_pct", DEFAULTS["stop_loss_pct"]))
    trail = float(cfg.get("trailing_stop_pct", DEFAULTS["trailing_stop_pct"]))
    activation = float(cfg.get("ts_activation_pct", DEFAULTS["ts_activation_pct"]))
    avg_win = float(m.get("avg_win") or 0.0)
    avg_loss = float(m.get("avg_loss") or 0.0)
    pf = float(m.get("profit_factor") or 0.0)

    # If losses are the problem, tighten only the stop loss. This matches the system theory:
    # wrong initial direction should be chopped quickly.
    if avg_loss > 0 and (pf < 1.0 or avg_loss > max(avg_win * 0.75, 0.01)):
        old = sl
        sl = max(MIN_FLOOR_SL, sl * (1 - STEP))
        if round(sl, 2) != round(old, 2):
            changes.append(f"SL {old:.2f}→{sl:.2f} (losses too large; avg_loss={avg_loss:.2f}, pf={pf:.2f})")

    # If winners are getting clipped small by trailing stop, LOOSEN the trailing distance.
    # This avoids trimming normal profit movement.
    if m.get("ts_win_count", 0) >= 2 and avg_win > 0 and avg_loss > 0 and avg_win < (avg_loss * 1.5):
        old = trail
        trail = min(MAX_TRAIL, trail * (1 + STEP))
        if round(trail, 2) != round(old, 2):
            changes.append(f"TRAIL {old:.2f}→{trail:.2f} (TS wins too small vs losses)")
    elif pf < 0.8 and m.get("sl_loss_count", 0) >= 3:
        # Losing badly: do not loosen trail. Leave it alone and let SL do the cutting.
        pass

    # Activation should not be below the stop. Arm the trail only once there is enough profit
    # to protect, otherwise it becomes a profit shredder.
    target_activation = max(MIN_TS_ACTIVATION, min(MAX_TS_ACTIVATION, max(sl, trail)))
    if round(target_activation, 2) != round(activation, 2):
        changes.append(f"TS_ACT {activation:.2f}→{target_activation:.2f} (arm trail after useful profit)")
        activation = target_activation

    # Cooldown rises after repeated losses, falls back slowly once PF is healthy.
    cooldown = int(cfg.get("cooldown_minutes", DEFAULTS["cooldown_minutes"]))
    if pf < 1.0:
        new_cd = min(60, max(cooldown, cooldown + 2))
    elif pf >= 1.5:
        new_cd = max(3, cooldown - 1)
    else:
        new_cd = cooldown
    if new_cd != cooldown:
        changes.append(f"COOLDOWN {cooldown}→{new_cd}m")
        cooldown = new_cd

    new["stop_loss_pct"] = round(sl, 2)
    new["trailing_stop_pct"] = round(trail, 2)
    new["ts_activation_pct"] = round(activation, 2)
    new["cooldown_minutes"] = cooldown
    return new, changes


def _record_tune(market: str, old_cfg: dict, new_cfg: dict, changes: list[str], metrics: dict) -> None:
    with db_cursor() as (_, cursor):
        cursor.execute(
            "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
            (
                "INFO",
                "market_tuner",
                f"TUNE {market}: {'; '.join(changes)} | "
                f"WR {metrics['win_rate']:.0%} PF {metrics['profit_factor']:.2f} "
                f"avgW {metrics['avg_win']:.2f} avgL {metrics['avg_loss']:.2f}",
            ),
        )


def tune_if_losing(market: str) -> Dict[str, Any]:
    """Called after a trade closes. Tunes SL/TS/cooldown only after a losing streak."""
    streak = _consecutive_losses(market)
    if streak < CONSECUTIVE_LOSSES_TO_TUNE:
        return {"action": "none", "streak": streak}

    metrics = _metrics(market)
    old_cfg = _get_config(market)
    new_cfg, changes = _apply_tune(old_cfg, metrics)

    if not changes or new_cfg == old_cfg:
        return {"action": "hold", "streak": streak, "metrics": metrics, "reason": "; ".join(changes) if changes else "no safe tune"}

    _save_config(market, new_cfg)
    _record_tune(market, old_cfg, new_cfg, changes, metrics)
    logger.warning("MarketTuner %s: %d losses → %s", market, streak, "; ".join(changes))
    return {"action": "tune", "streak": streak, "old": old_cfg, "new": new_cfg, "changes": changes, "metrics": metrics}
