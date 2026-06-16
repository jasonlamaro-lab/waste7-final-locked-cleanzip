"""
Swarm Learning — shared pattern knowledge across all markets.
"""
from typing import Optional
from core.db import db_cursor
from core.logger import logger

SWARM_GATE_THRESHOLD = 3


def _wps_band(wps: float) -> str:
    if wps >= 70:
        return "HIGH"
    elif wps >= 40:
        return "MED"
    else:
        return "LOW"


def _pattern_key(regime: str, wps: float) -> str:
    return f"{regime.upper()}_{_wps_band(wps)}"


def record_pattern_outcome(market: str, regime: str, wps: float, won: bool):
    """Track every pattern outcome: losses build soft-gates, wins build confidence."""
    key = _pattern_key(regime, wps)
    with db_cursor() as (conn, cursor):
        if won:
            cursor.execute("""
                INSERT INTO swarm_patterns (pattern_key, flagging_market, outcome, regime, wps_band, wins)
                VALUES (?, ?, 'WIN', ?, ?, 1)
                ON CONFLICT(pattern_key, flagging_market) DO UPDATE SET
                    wins = wins + 1,
                    outcome = CASE WHEN wins + 1 > vote_count THEN 'WIN' ELSE outcome END
            """, (key, market, regime.upper(), _wps_band(wps)))
            # Winning patterns can REVOKE a soft gate if wins overwhelm losses
            cursor.execute(
                "SELECT SUM(wins), SUM(vote_count) FROM swarm_patterns WHERE pattern_key = ?",
                (key,)
            )
            wins_total, losses_total = cursor.fetchone()
            wins_total = wins_total or 0
            losses_total = losses_total or 0
            if wins_total > losses_total * 2:  # 2x wins → revoke gate
                cursor.execute(
                    "UPDATE swarm_patterns SET soft_gate_active = 0 WHERE pattern_key = ?",
                    (key,)
                )
            return

        # LOSS path (original)
        cursor.execute("""
            INSERT INTO swarm_patterns (pattern_key, flagging_market, outcome, regime, wps_band)
            VALUES (?, ?, 'LOSS', ?, ?)
            ON CONFLICT(pattern_key, flagging_market) DO UPDATE SET
                vote_count = vote_count + 1,
                outcome = 'LOSS'
        """, (key, market, regime.upper(), _wps_band(wps)))

        cursor.execute(
            "SELECT COUNT(DISTINCT flagging_market) FROM swarm_patterns WHERE pattern_key = ? AND outcome = 'LOSS'",
            (key,)
        )
        vote_count = cursor.fetchone()[0]

        if vote_count >= SWARM_GATE_THRESHOLD:
            cursor.execute(
                "UPDATE swarm_patterns SET soft_gate_active = 1 WHERE pattern_key = ?",
                (key,)
            )
            cursor.execute(
                "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
                ("WARN", "swarm", f"Soft gate ACTIVATED for pattern {key} ({vote_count} markets flagged)")
            )
            logger.warning("Swarm: soft gate activated for pattern %s (%d markets)", key, vote_count)


def is_pattern_gated(regime: str, wps: float) -> bool:
    key = _pattern_key(regime, wps)
    with db_cursor() as (conn, cursor):
        cursor.execute(
            "SELECT soft_gate_active FROM swarm_patterns WHERE pattern_key = ? LIMIT 1",
            (key,)
        )
        row = cursor.fetchone()
        return bool(row and row[0])


def get_swarm_summary() -> dict:
    with db_cursor() as (conn, cursor):
        cursor.execute("""
            SELECT pattern_key, SUM(vote_count) as total_votes,
                   MAX(soft_gate_active) as gated,
                   GROUP_CONCAT(DISTINCT flagging_market) as markets
            FROM swarm_patterns
            GROUP BY pattern_key
            ORDER BY total_votes DESC
        """)
        rows = cursor.fetchall()
        patterns = [
            {
                "pattern": r[0],
                "votes": r[1],
                "gated": bool(r[2]),
                "markets": r[3].split(",") if r[3] else [],
            }
            for r in rows
        ]
    return {
        "patterns": patterns,
        "active_gates": sum(1 for p in patterns if p["gated"]),
    }
