from core.risk import can_trade
from core.gates import GateContext, run_gates
from services.execution.trade_executor import execute_trade
from core.logger import logger
from core.db import db_cursor

# Per-engine trade limits — ensures each engine gets capital
ENGINE_MAX_TRADES = {
    "equity": 5,
}


def _engine_open_count(engine: str) -> int:
    try:
        with db_cursor() as (conn, cursor):
            cursor.execute(
                "SELECT COUNT(*) FROM trades WHERE engine = ? AND status = 'OPEN'",
                (engine,)
            )
            return int(cursor.fetchone()[0])
    except Exception:
        return 0


def _has_open_position(symbol: str) -> bool:
    try:
        with db_cursor() as (conn, cursor):
            cursor.execute(
                "SELECT id FROM trades WHERE symbol = ? AND status IN ('OPEN','PENDING') LIMIT 1",
                (symbol,)
            )
            return cursor.fetchone() is not None
    except Exception as exc:
        logger.warning("_has_open_position check failed for %s: %s", symbol, exc)
        return False


def _loss_cooldown_active(symbol: str) -> tuple[bool, int]:
    """
    After a losing trade, enforce a cooldown before re-entering the same market.
    Cooldown scales with consecutive losses:
      1 loss  → 15 min
      2 losses → 30 min
      3+ losses → 60 min
    Returns (cooldown_active, minutes_remaining).
    """
    try:
        from core.trade_style import get_style
        style = get_style()
        # SCALP gets shorter cooldowns — losses are expected more often
        base_minutes = {"SCALP": 3, "SWING": 10, "HOLD": 20}.get(style["name"], 10)
    except Exception:
        base_minutes = 15

    try:
        with db_cursor() as (conn, cursor):
            # Find the last closed trade for this market
            cursor.execute("""
                SELECT pnl, closed_at FROM trades
                WHERE symbol = ? AND status = 'CLOSED'
                ORDER BY id DESC LIMIT 5
            """, (symbol,))
            rows = cursor.fetchall()
    except Exception:
        return False, 0

    if not rows:
        return False, 0

    # Count consecutive losses from most recent
    consecutive = 0
    for pnl, _ in rows:
        if (pnl or 0) <= 0:
            consecutive += 1
        else:
            break

    if consecutive == 0:
        return False, 0

    # Scale cooldown with streak
    cooldown_mins = base_minutes * min(consecutive, 3)  # cap at 3x
    last_close_str = rows[0][1]  # most recent closed_at

    try:
        from datetime import datetime, timezone
        # SQLite stores CURRENT_TIMESTAMP as UTC without timezone info
        last_close = datetime.strptime(last_close_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        elapsed_mins = (now - last_close).total_seconds() / 60.0
        remaining = cooldown_mins - elapsed_mins
        if remaining > 0:
            return True, int(remaining)
    except Exception:
        pass

    return False, 0


def _open_trade_count() -> int:
    try:
        with db_cursor() as (conn, cursor):
            cursor.execute("SELECT COUNT(*) FROM trades WHERE status IN ('OPEN','PENDING')")
            return int(cursor.fetchone()[0])
    except Exception:
        return 0


def _daily_loss_pct() -> float:
    """Return today's realised loss as a % of current kitty balance."""
    try:
        with db_cursor() as (conn, cursor):
            cursor.execute(
                """SELECT COALESCE(SUM(pnl), 0) FROM trades
                   WHERE status = 'CLOSED' AND date(closed_at) = date('now') AND pnl < 0"""
            )
            loss = abs(float(cursor.fetchone()[0]))
            cursor.execute("SELECT balance FROM kitty WHERE id = 1")
            row = cursor.fetchone()
            balance = float(row[0]) if row else 10000.0
            return (loss / balance * 100) if balance > 0 else 0.0
    except Exception:
        return 0.0


def maybe_execute_trade(engine: str, symbol: str, side: str, price: float, reason: str,
                        pf: float = 3.0, accuracy: float = 70.0, health: float = 80.0,
                        wps: float = 50.0, regime: str = "NEUTRAL",
                        anchor_symbol: str = None,
                        timeframes: dict = None,
                        confidence: float = 0.5,
                        alignment: int = 0):
    from core.state import STATE
    from core.config import MAX_CONCURRENT_TRADES, STOP_LOSS_PCT, TRAILING_STOP_PCT

    if STATE.get("paused"):
        return None

    if not can_trade():
        logger.info("Trade blocked: max concurrent trades reached")
        return None

    if _has_open_position(symbol):
        logger.info("Trade blocked: already have an open position on %s", symbol)
        return None

    # Loss cooldown — delay re-entry after losses to avoid compounding bad conditions
    cooldown_active, mins_remaining = _loss_cooldown_active(symbol)
    if cooldown_active:
        logger.info("Trade blocked: %s in loss cooldown, %d min remaining", symbol, mins_remaining)
        return None

    # Exchange hours check — only trade during regular session
    try:
        from engines.equity.market_hours import is_market_open
        if not is_market_open(symbol):
            logger.debug("Trade blocked: %s exchange is closed", symbol)
            return None
    except Exception as exc:
        logger.warning("Market hours check failed for %s: %s", symbol, exc)

    # Build gate context from available signal data
    ctx = GateContext(
        timeframes=timeframes or {},
        wps=wps,
        confidence=confidence,
        regime=regime,
        alignment=alignment,
        api_ok=True,
        data_feed_ok=True,
        latency_ms=0.0,
        open_trade_count=_open_trade_count(),
        max_concurrent=MAX_CONCURRENT_TRADES,
        stop_loss_pct=STOP_LOSS_PCT,
        trailing_stop_pct=TRAILING_STOP_PCT,
        daily_loss_pct=_daily_loss_pct(),
        daily_loss_limit_pct=10.0,
    )

    pipeline = run_gates(ctx, market=symbol)
    if not pipeline.passed:
        logger.info("Trade blocked by %s gate: %s — %s",
                    pipeline.failed_at,
                    pipeline.results[-1].reason,
                    pipeline.summary())
        return None

    logger.debug("Gates passed: %s", pipeline.summary())

    try:
        from services.lifecycle.market_lifecycle import is_trading_allowed
        if not is_trading_allowed(symbol):
            logger.info("Trade blocked: %s lifecycle state is DEGRADED/RESET", symbol)
            return None
    except Exception as exc:
        logger.warning("Lifecycle check failed for %s: %s", symbol, exc)

    try:
        from services.intelligence.swarm_learning import is_pattern_gated
        if is_pattern_gated(regime, wps):
            logger.info("Trade blocked: swarm gate active for %s regime=%s wps=%.1f", symbol, regime, wps)
            return None
    except Exception as exc:
        logger.warning("Swarm gate check failed for %s: %s", symbol, exc)

    try:
        from services.intelligence.auto_optimizer import is_market_suppressed
        if is_market_suppressed(symbol):
            logger.info("Trade blocked: %s in rolling loss backoff (5 consecutive losses)", symbol)
            return None
    except Exception as exc:
        logger.warning("Auto-optimizer suppressor check failed for %s: %s", symbol, exc)

    stake = 50.0
    kitty_level = 1
    is_live_market = False
    try:
        from services.lifecycle.market_lifecycle import is_live
        from services.capital.kitty_manager import get_next_level, reserve_stake, _get_base
        is_live_market = is_live(symbol)
        stake = _get_base()
        kitty_level = get_next_level(symbol)
        result = reserve_stake(symbol, kitty_level)
        if result is not None:
            stake, kitty_level = result
    except Exception as exc:
        logger.warning("Kitty check failed for %s: %s", symbol, exc)

    trade = execute_trade(
        engine=engine,
        symbol=symbol,
        side=side,
        price=price,
        reason=reason,
        size=stake,
        kitty_level=kitty_level,
        is_sim=not is_live_market,
        anchor_symbol=anchor_symbol,
    )
    if trade:
        logger.info(
            "Trade executed: %s %s @ %.4f | level=%d stake=%.2f sim=%s gates=%s",
            side, symbol, price, kitty_level, stake, not is_live_market,
            pipeline.summary()
        )
    return trade
