"""
Market Lifecycle Manager — SIM -> LIVE -> DEGRADED -> RESET
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional
from core.db import db_cursor
from core.logger import logger

ELITE_PF = 1.5
ELITE_WIN_RATE = 0.60
ELITE_EXPECTANCY = 0.05   # +$0.05/trade minimum, performance-based gate
BRAINWASH_WIN_RATE = 0.35
BRAINWASH_MIN_TRADES = 8


def get_market_state(market: str) -> Dict[str, Any]:
    with db_cursor() as (conn, cursor):
        cursor.execute("SELECT * FROM market_state WHERE market = ?", (market,))
        row = cursor.fetchone()
        if not row:
            _ensure_market_state(cursor, market)
            conn.commit()
            cursor.execute("SELECT * FROM market_state WHERE market = ?", (market,))
            row = cursor.fetchone()
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))


def _ensure_market_state(cursor, market: str):
    cursor.execute(
        "INSERT OR IGNORE INTO market_state (market) VALUES (?)", (market,)
    )


def update_market_stats(market: str, pnl: float, won: bool, regime_correct: Optional[bool] = None):
    with db_cursor() as (conn, cursor):
        _ensure_market_state(cursor, market)
        cursor.execute("SELECT * FROM market_state WHERE market = ?", (market,))
        row = cursor.fetchone()
        cols = [d[0] for d in cursor.description]
        state = dict(zip(cols, row))

        win_count = state["win_count"] + (1 if won else 0)
        loss_count = state["loss_count"] + (0 if won else 1)
        total_trades = win_count + loss_count
        total_pnl = state["total_pnl"] + pnl

        win_rate = win_count / total_trades if total_trades > 0 else 0.0

        if regime_correct is not None:
            old_acc = state["regime_accuracy"]
            old_count = max(total_trades - 1, 1)
            regime_accuracy = (old_acc * old_count + (1.0 if regime_correct else 0.0)) / (old_count + 1)
        else:
            regime_accuracy = state["regime_accuracy"]

        if loss_count > 0 and win_count > 0:
            loss_rate = 1 - win_rate
            profit_factor = min(999.0, win_rate / loss_rate) if loss_rate > 0 else 999.0
        else:
            profit_factor = win_rate * 3

        sim_trades = state["sim_trades"] + (1 if state["lifecycle"] == "SIM" else 0)

        cursor.execute("""
            UPDATE market_state SET
                win_count = ?, loss_count = ?, total_pnl = ?,
                profit_factor = ?, win_rate = ?, regime_accuracy = ?,
                sim_trades = ?, updated_at = CURRENT_TIMESTAMP
            WHERE market = ?
        """, (win_count, loss_count, total_pnl, profit_factor, win_rate, regime_accuracy, sim_trades, market))

    _check_lifecycle_transition(market, {
        "lifecycle": state["lifecycle"],
        "win_count": win_count,
        "loss_count": loss_count,
        "total_pnl": total_pnl,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "regime_accuracy": regime_accuracy,
        "sim_trades": sim_trades,
        "brain_wash_count": state["brain_wash_count"],
    })


def _check_lifecycle_transition(market: str, stats: Dict):
    lc = stats["lifecycle"]
    total_trades = stats["win_count"] + stats["loss_count"]
    win_rate = stats["win_rate"]

    if lc == "SIM":
        # Performance-based graduation (no trade-count minimum).
        # Market must hit win rate + profit factor + expectancy thresholds.
        total_trades = stats["win_count"] + stats["loss_count"]
        expectancy = (stats["total_pnl"] / total_trades) if total_trades > 0 else 0.0
        if (
            stats["profit_factor"] >= ELITE_PF
            and win_rate >= ELITE_WIN_RATE
            and expectancy >= ELITE_EXPECTANCY
        ):
            _transition(market, "LIVE",
                        f"Performance gate hit: PF={stats['profit_factor']:.2f} "
                        f"WR={win_rate:.1%} Expectancy=${expectancy:+.3f}")

    elif lc == "LIVE":
        if total_trades >= BRAINWASH_MIN_TRADES and win_rate < BRAINWASH_WIN_RATE:
            _brain_wash(market, f"LIVE win rate {win_rate:.1%} below {BRAINWASH_WIN_RATE:.0%}")

    elif lc == "DEGRADED":
        if total_trades >= BRAINWASH_MIN_TRADES and win_rate < BRAINWASH_WIN_RATE:
            _brain_wash(market, f"Degraded win rate {win_rate:.1%} still below {BRAINWASH_WIN_RATE:.0%}")
        elif win_rate >= ELITE_WIN_RATE and stats["profit_factor"] >= ELITE_PF:
            _transition(market, "SIM", f"Recovered: WR={win_rate:.1%} PF={stats['profit_factor']:.2f}")


def _transition(market: str, new_lifecycle: str, reason: str):
    with db_cursor() as (conn, cursor):
        cursor.execute(
            "UPDATE market_state SET lifecycle = ?, updated_at = CURRENT_TIMESTAMP WHERE market = ?",
            (new_lifecycle, market)
        )
        cursor.execute(
            "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
            ("INFO", "lifecycle", f"{market} -> {new_lifecycle}: {reason}")
        )
    logger.info("Lifecycle: %s -> %s — %s", market, new_lifecycle, reason)


def _brain_wash(market: str, reason: str):
    with db_cursor() as (conn, cursor):
        cursor.execute("SELECT brain_wash_count FROM market_state WHERE market = ?", (market,))
        row = cursor.fetchone()
        bwc = (row[0] + 1) if row else 1
        cursor.execute("""
            UPDATE market_state SET
                lifecycle = 'SIM',
                win_count = 0,
                loss_count = 0,
                total_pnl = 0.0,
                profit_factor = 0.0,
                win_rate = 0.0,
                regime_accuracy = 0.0,
                sim_trades = 0,
                brain_wash_count = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE market = ?
        """, (bwc, market))
        cursor.execute(
            "INSERT INTO resets (scope, detail) VALUES (?, ?)",
            (market, f"Brain wash #{bwc}: {reason}")
        )
        cursor.execute(
            "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
            ("WARN", "lifecycle", f"BRAIN WASH #{bwc} for {market}: {reason}")
        )
    logger.warning("BRAIN WASH: %s (count=%d) — %s", market, bwc, reason)


def is_live(market: str) -> bool:
    state = get_market_state(market)
    return state["lifecycle"] == "LIVE"


def is_trading_allowed(market: str) -> bool:
    state = get_market_state(market)
    return state["lifecycle"] in ("SIM", "LIVE")


def get_all_lifecycle_states() -> Dict[str, Dict]:
    with db_cursor() as (conn, cursor):
        cursor.execute("SELECT * FROM market_state ORDER BY market")
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return {row[0]: dict(zip(cols, row)) for row in rows}
