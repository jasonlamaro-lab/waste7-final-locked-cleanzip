"""
KittyManager — single-pool balance accounting.

Philosophy (SACRED):
  - Trade OPEN  → balance -= stake          (stake immediately deducted)
  - Trade CLOSE → balance += stake + pnl    (stake returned + pnl applied)
  - No "reserved" concept. balance is the one true number.
  - If balance ever ≤ 0, auto-reset to KITTY_RESET_BALANCE ($10,000).

The faceplate reads kitty.balance directly — no client-side math.
"""
import os
import threading
from typing import Optional, Tuple
from core.config import BROKER_FEE_PCT
from core.db import db_cursor
from core.logger import logger

_lock = threading.Lock()
KITTY_RESET_BALANCE = 10000.0


def _build_ladder(base: float) -> list:
    return [round(base * (2 ** i), 2) for i in range(5)]


def _get_base() -> float:
    """Read BASE_TRADE_AMOUNT from env (updated live via settings API → os.environ)."""
    try:
        return float(os.getenv("BASE_TRADE_AMOUNT", "2.0"))
    except Exception:
        return 2.0


def get_kitty() -> dict:
    with db_cursor() as (conn, cursor):
        cursor.execute("SELECT balance FROM kitty WHERE id = 1")
        row = cursor.fetchone()
        if row:
            bal = float(row[0])
            return {"balance": bal, "reserved": 0.0, "available": bal}
        return {"balance": 0.0, "reserved": 0.0, "available": 0.0}


def _autoreset_if_depleted(cursor, balance: float, market: str = None) -> float:
    """If balance ≤ 0, reset to KITTY_RESET_BALANCE and log RESET event."""
    if balance <= 0:
        logger.warning("KittyManager: balance depleted (A$%.2f) — auto-reset to A$%.2f",
                       balance, KITTY_RESET_BALANCE)
        cursor.execute(
            "UPDATE kitty SET balance = ?, reserved = 0.0, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (KITTY_RESET_BALANCE,)
        )
        cursor.execute(
            "INSERT INTO kitty_history (event, amount, balance_after, market) VALUES (?, ?, ?, ?)",
            ("RESET", KITTY_RESET_BALANCE - balance, KITTY_RESET_BALANCE, market)
        )
        return KITTY_RESET_BALANCE
    return balance


def reserve_stake(market: str, level: int) -> Optional[Tuple[float, int]]:
    """
    Deduct the full stake from balance IMMEDIATELY on trade open.
    No reservation, no capital gate — if balance goes ≤ 0 we auto-reset on the
    next settlement. Returns (stake, level) always.
    """
    ladder = _build_ladder(_get_base())
    if level < 1 or level > len(ladder):
        level = 1
    stake = ladder[level - 1]

    with _lock:
        with db_cursor() as (conn, cursor):
            cursor.execute("SELECT balance FROM kitty WHERE id = 1")
            row = cursor.fetchone()
            if not row:
                return None
            balance = float(row[0])
            new_balance = round(balance - stake, 4)
            cursor.execute(
                "UPDATE kitty SET balance = ?, reserved = 0.0, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (new_balance,)
            )
            cursor.execute(
                "INSERT INTO kitty_history (event, amount, balance_after, market) VALUES (?, ?, ?, ?)",
                ("OPEN", -stake, new_balance, market)
            )
            _autoreset_if_depleted(cursor, new_balance, market)

    logger.info("KittyManager: OPEN -A$%.2f for %s → balance A$%.2f", stake, market, new_balance)
    return (stake, level)


def settle_trade(market: str, trade_id: int, pnl_pct: float, stake: float, won: bool) -> None:
    """
    On trade CLOSE: balance += (stake + dollar_pnl).
    The full stake returns; the dollar pnl is then applied on top.
    Brokerage fee is netted out of pnl as before.
    """
    dollar_pnl = stake * pnl_pct / 100.0
    broker_fee = stake * BROKER_FEE_PCT / 100.0
    net_pnl = dollar_pnl - broker_fee
    delta = stake + net_pnl  # stake returned + net pnl

    with _lock:
        with db_cursor() as (conn, cursor):
            cursor.execute("SELECT balance FROM kitty WHERE id = 1")
            row = cursor.fetchone()
            if not row:
                return
            balance = float(row[0])
            new_balance = round(balance + delta, 4)

            cursor.execute(
                "UPDATE kitty SET balance = ?, reserved = 0.0, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (new_balance,)
            )
            event = "WIN" if won else "LOSS"
            # Store the net dollar P&L (not the full delta) so history shows
            # actual gain/loss not stake-return combined
            cursor.execute(
                "INSERT INTO kitty_history (event, amount, balance_after, market, trade_id) VALUES (?, ?, ?, ?, ?)",
                (event, round(net_pnl, 4), new_balance, market, trade_id)
            )
            if broker_fee > 0:
                cursor.execute(
                    "INSERT INTO kitty_history (event, amount, balance_after, market, trade_id) VALUES (?, ?, ?, ?, ?)",
                    ("FEE", round(-broker_fee, 4), new_balance, market, trade_id)
                )
            new_balance = _autoreset_if_depleted(cursor, new_balance, market)

    logger.info(
        "KittyManager: %s %s pnl_pct=%.2f%% stake=A$%.2f dollar_pnl=A$%.4f fee=A$%.4f delta=A$%+.4f balance=A$%.4f",
        event, market, pnl_pct, stake, dollar_pnl, broker_fee, delta, new_balance
    )

    # Mode-A removed: WPS thresholds are owned by Auto-Optimizer + manual overrides only.


def get_next_level(market: str) -> int:
    # Fixed at level 1 — every trade is base amount, no martingale doubling
    return 1


def get_kitty_summary() -> dict:
    kitty = get_kitty()
    with db_cursor() as (conn, cursor):
        cursor.execute(
            "SELECT event, amount, balance_after, market, created_at FROM kitty_history ORDER BY id DESC LIMIT 20"
        )
        history = [
            {"event": r[0], "amount": r[1], "balance_after": r[2], "market": r[3], "created_at": r[4]}
            for r in cursor.fetchall()
        ]
    live_ladder = _build_ladder(_get_base())
    return {
        "balance": kitty["balance"],
        "reserved": kitty["reserved"],
        "available": kitty["available"],
        "base_trade_amount": _get_base(),
        "ladder": live_ladder,
        "max_exposure": sum(live_ladder),
        "history": history,
    }
