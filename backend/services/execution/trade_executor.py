import os
from core.db import db_cursor
from core.logger import logger


def _read_risk_params():
    """Read SL/TS from environment (updated live via settings API → os.environ)."""
    sl = float(os.getenv("STOP_LOSS_PCT", "2.0"))
    ts = float(os.getenv("TRAILING_STOP_PCT", "1.5"))
    return sl, ts


def _compute_stop_loss(side: str, price: float) -> float:
    sl, _ = _read_risk_params()
    if side == "BUY":
        return price * (1 - sl / 100)
    else:
        return price * (1 + sl / 100)


def _compute_trailing_stop(side: str, price: float) -> float:
    # Trailing stop is not yet activated at entry; return 0.0 to indicate
    # "not active". The actual TS trigger is managed dynamically in trade_manager.py
    # using peak_pnl_dollars once TS_ACTIVATION is reached.
    return 0.0


def _broker_is_ready() -> bool:
    """True only if IG Markets broker connection is active."""
    try:
        from services.execution import ig_broker
        return bool(ig_broker._state.get("connected"))
    except Exception:
        return False


def simulate_trade(
    engine: str, symbol: str, side: str, price: float, reason: str,
    size: float = 2.0, kitty_level: int = 1, is_sim: bool = True,
    anchor_symbol: str = None,
):
    stop_loss_price = _compute_stop_loss(side, price)
    trailing_stop_price = _compute_trailing_stop(side, price)
    peak_price = price

    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO trades (
                engine, symbol, side, entry_price, current_price,
                status, pnl, reason,
                stop_loss_price, trailing_stop_price, peak_price,
                size, kitty_level, is_sim, anchor_symbol
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                engine, symbol, side, price, price,
                "OPEN", -0.10, reason,
                stop_loss_price, trailing_stop_price, peak_price,
                size, kitty_level, 1 if is_sim else 0, anchor_symbol,
            )
        )

    logger.info(
        "Trade: %s %s %s @ %.4f  anchor=%s  SL=%.4f  trail=%.4f  size=%.2f  level=%d  sim=%s",
        engine, symbol, side, price, anchor_symbol, stop_loss_price, trailing_stop_price,
        size, kitty_level, is_sim
    )
    return {
        "engine": engine, "symbol": symbol, "side": side, "price": price,
        "reason": reason, "status": "OPEN", "size": size,
        "kitty_level": kitty_level, "is_sim": is_sim,
        "stop_loss_price": stop_loss_price,
        "trailing_stop_price": trailing_stop_price,
        "anchor_symbol": anchor_symbol,
    }


def execute_trade(
    engine: str, symbol: str, side: str, price: float, reason: str,
    size: float = 2.0, kitty_level: int = 1, is_sim: bool = True,
    anchor_symbol: str = None,
):
    """All trades run as SIM until broker mode is explicitly re-enabled."""
    # SIM-only mode: no broker connection regardless of lifecycle state
    return simulate_trade(engine, symbol, side, price, reason,
                          size=size, kitty_level=kitty_level, is_sim=True,
                          anchor_symbol=anchor_symbol)
