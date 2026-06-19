"""
Trade Manager — updates open trades with current prices, checks SL/TS/TP/time triggers.
"""
import requests
from datetime import datetime, timedelta
import os
from core.config import BROKER_FEE_PCT
from core.db import db_cursor
from core.logger import logger

TAKE_PROFIT_PCT = 999999.0  # disabled — exits via SL or TS only
TIME_EXIT_MINUTES = 15  # auto-close any trade after 15 minutes max


def _read_risk_params(symbol: str = None):
    """Read SL/TS/TS_ACTIVATION.

    Order of authority:
      1. Active trade style / env settings provide the base.
      2. Per-market market_state.config overrides can narrow/widen SL/TS/activation.

    This lets Market Tuner tune trade management per market without touching WPS/CONF gates.
    Returns (SL_PCT, TS_PCT, TS_ACTIVATION_PCT) as % of stake.
    """
    # Defaults from active style
    try:
        from core.trade_style import get_sl_ts
        sl, ts, ts_act = get_sl_ts()
    except Exception:
        sl, ts, ts_act = 1.50, 1.00, 0.80

    # Allow env vars to override individual values (set via settings API → os.environ)
    try:
        sl = float(os.getenv("STOP_LOSS_PCT", str(sl)))
        ts = float(os.getenv("TRAILING_STOP_PCT", str(ts)))
        ts_act = float(os.getenv("TS_ACTIVATION_PCT", str(ts_act)))
    except Exception:
        pass

    if symbol:
        try:
            import json
            with db_cursor() as (_, cur):
                cur.execute("SELECT config FROM market_state WHERE market = ?", (symbol,))
                row = cur.fetchone()
            if row and row[0]:
                cfg = json.loads(row[0]) or {}
                sl = float(cfg.get("stop_loss_pct", sl))
                ts = float(cfg.get("trailing_stop_pct", ts))
                ts_act = float(cfg.get("ts_activation_pct", ts_act))
        except Exception:
            pass

    return sl, ts, ts_act


def _fetch_current_price(symbol: str, engine: str, anchor_symbol: str = None) -> float:
    """Get current price for an equity market.

    Primary path: EODHD real-time API (paid, reliable, low-latency).
    Fallback: yfinance (free but throttled/intermittent).

    If anchor_symbol is provided, fetch THAT exact ticker — the same one used
    at entry. This guarantees entry_price and current_price are comparable.
    Legacy trades (NULL anchor) iterate dynamic constituents and pick the
    first one that returns a valid price.
    """
    # Build the list of tickers to try, in order
    tickers_to_try = []
    if anchor_symbol:
        tickers_to_try.append(anchor_symbol)
    else:
        try:
            from engines.equity.constituent_refresh import get_constituents
            dyn = get_constituents(symbol) or {}
            for sym in (dyn.get("constituents") or {}).keys():
                tickers_to_try.append(sym)
        except Exception:
            pass
        if not tickers_to_try:
            from engines.equity.markets import MARKET_DEFINITIONS
            defn = MARKET_DEFINITIONS.get(symbol)
            if defn:
                tickers_to_try.extend(defn["constituents"].keys())

    if not tickers_to_try:
        return 0.0

    # PRIMARY: Yahoo Finance
    try:
        from services.data import yahoo_client
        for top_sym in tickers_to_try:
            p = yahoo_client.get_price(top_sym)
            if p > 0:
                return float(p)
    except Exception as exc:
        logger.debug("Yahoo lookup failed for %s: %s", symbol, exc)

    # FALLBACK: yfinance
    try:
        import yfinance as yf
        for top_sym in tickers_to_try:
            try:
                ticker = yf.Ticker(top_sym)
                data = ticker.fast_info
                price = getattr(data, 'last_price', None) or getattr(data, 'previous_close', None)
                if price and price > 0:
                    return float(price)
            except Exception:
                continue
    except Exception:
        pass
    return 0.0


def update_open_trades():
    """Update all open trades with current prices, check stop loss and trailing stop."""
    # Auto-expire any LIVE PENDING trades that didn't get a broker confirmation
    # within 60s — prevents zombie rows from blocking re-entry on the symbol.
    with db_cursor() as (conn, cursor):
        cursor.execute("""
            UPDATE trades SET status='REJECTED', broker_status='TIMEOUT',
                broker_error='no broker confirmation within 60s',
                closed_at=CURRENT_TIMESTAMP
            WHERE is_sim=0 AND status='PENDING'
              AND created_at < datetime('now', '-60 seconds')
        """)
        if cursor.rowcount:
            logger.warning("Auto-expired %d stuck PENDING LIVE trade(s)", cursor.rowcount)

    # Sync kitty reserved to actual LIVE open trade stakes only (SIM trades don't count)
    with db_cursor() as (conn, cursor):
        actual = cursor.execute("SELECT COALESCE(SUM(size), 0) FROM trades WHERE status = 'OPEN' AND is_sim = 0").fetchone()[0]
        cursor.execute("UPDATE kitty SET reserved = ? WHERE id = 1", (actual,))

    with db_cursor() as (conn, cursor):
        cursor.execute("""
            SELECT id, engine, symbol, side, entry_price, current_price,
                   stop_loss_price, peak_pnl_dollars,
                   size, kitty_level, is_sim, created_at, broker_position_id,
                   anchor_symbol
            FROM trades WHERE status = 'OPEN'
        """)
        open_trades = cursor.fetchall()

    if not open_trades:
        return

    cols = ["id", "engine", "symbol", "side", "entry_price", "current_price",
            "stop_loss_price", "peak_pnl_dollars",
            "size", "kitty_level", "is_sim", "created_at", "broker_position_id",
            "anchor_symbol"]

    for row in open_trades:
        trade = dict(zip(cols, row))
        trade_id = trade["id"]
        new_price = _fetch_current_price(
            trade["symbol"], trade["engine"], anchor_symbol=trade.get("anchor_symbol")
        )
        if new_price <= 0:
            continue

        side = trade["side"]
        entry = trade["entry_price"]
        stake = trade.get("size") or 2.0       # trade_risk in dollars

        # P&L on the underlying (percent) and on the trade stake (dollars)
        if side == "BUY":
            pnl_pct = ((new_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - new_price) / entry) * 100
        current_profit = (pnl_pct / 100.0) * stake     # $ on the stake

        # Track peak $ P&L (max profit ever reached on this trade)
        peak_profit = trade.get("peak_pnl_dollars") or 0.0
        if current_profit > peak_profit:
            peak_profit = current_profit

        # Risk thresholds — SL and TS are the ONLY exit mechanisms.
        SL_PCT, TS_PCT, TS_ACT_PCT = _read_risk_params(trade["symbol"])
        SL_dollars    = stake * (SL_PCT / 100.0)
        TS_dollars    = stake * (TS_PCT / 100.0)
        TS_activation = stake * (TS_ACT_PCT / 100.0)

        # Stop loss — close when drawdown on stake hits SL_dollars
        sl_hit = current_profit <= -SL_dollars

        # Trailing stop — arms once trade reaches TS_activation profit,
        # fires when it retraces TS_dollars from the peak.
        ts_hit = (
            current_profit >= TS_activation
            and (peak_profit - current_profit) >= TS_dollars
        )

        # Time exit — force-close any trade that has been open 15 minutes or more
        time_hit = False
        try:
            created_str = trade.get("created_at") or ""
            if created_str:
                from datetime import timezone
                created_dt = datetime.strptime(created_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                elapsed_mins = (datetime.now(timezone.utc) - created_dt).total_seconds() / 60.0
                time_hit = elapsed_mins >= TIME_EXIT_MINUTES
        except Exception as exc:
            logger.warning("Time-exit check failed for trade %d: %s", trade_id, exc)

        should_close = sl_hit or ts_hit or time_hit

        with db_cursor() as (conn, cursor):
            if should_close:
                close_reason = "SL_HIT" if sl_hit else ("TS_HIT" if ts_hit else "TIME_EXIT_15MIN")

                # Broker close disabled — SIM-only mode, no live execution.

                pnl_dollars = round(stake * pnl_pct / 100.0, 4)
                cursor.execute("""
                    UPDATE trades SET
                        current_price = ?, pnl = ?, pnl_pct = ?, pnl_dollars = ?,
                        peak_pnl_dollars = ?,
                        status = 'CLOSED', closed_at = CURRENT_TIMESTAMP,
                        reason = reason || ' | ' || ?
                    WHERE id = ?
                """, (new_price, round(pnl_pct, 4), round(pnl_pct, 4), pnl_dollars,
                      round(peak_profit, 4), close_reason, trade_id))

                # Settle with kitty — every close (SIM + LIVE).
                # Kitty is the user's accounting view; tracks all trade activity.
                try:
                    from services.capital.kitty_manager import settle_trade
                    stake = trade["size"] or 2.0
                    won = pnl_pct > 0
                    settle_trade(trade["symbol"], trade_id, pnl_pct, stake, won)
                except Exception as exc:
                    logger.warning("Kitty settle failed for trade %d: %s", trade_id, exc)

                # Notify on LIVE close only (broker disabled — no notifications)
                if False and not trade.get("is_sim"):
                    try:
                        from services.notifications.notifier import send as notify_send
                        stake = trade["size"] or 0
                        dollar = stake * pnl_pct / 100
                        verdict = "WIN" if pnl_pct > 0 else "LOSS"
                        notify_send(
                            subject=f"LIVE {verdict} {trade['symbol']} {dollar:+.2f} AUD",
                            body=(f"Trade #{trade_id} {trade['side']} {trade['symbol']} closed ({close_reason})\n"
                                  f"P&L: {pnl_pct:+.2f}% = A${dollar:+.2f}\n"
                                  f"Stake: A${stake:.2f}   Entry: {trade.get('entry_price')}   Exit: {new_price}"),
                            event_key=f"close-{trade_id}",
                        )
                    except Exception as exc:
                        logger.debug("Notifier (live close) failed: %s", exc)

                # Update lifecycle stats
                try:
                    from services.lifecycle.market_lifecycle import update_market_stats
                    update_market_stats(trade["symbol"], pnl_pct, pnl_pct > 0)
                except Exception as exc:
                    logger.warning("Lifecycle update failed for trade %d: %s", trade_id, exc)

                # Swarm learning — record pattern outcome (losses build gates, wins revoke them)
                try:
                    from services.intelligence.swarm_learning import record_pattern_outcome
                    # Extract regime from reason string
                    reason_str = trade.get("reason", "") or ""
                    regime = "NEUTRAL"
                    for r in ["TRENDING", "CHOPPY_HIGH", "CHOPPY_MEDIUM", "REVERSAL"]:
                        if r in reason_str:
                            regime = r
                            break
                    # Extract WPS from reason
                    import re
                    wps_match = re.search(r'WPS\s+([-\d.]+)', reason_str)
                    wps_val = float(wps_match.group(1)) if wps_match else 50.0
                    record_pattern_outcome(trade["symbol"], regime, wps_val, pnl_pct > 0)
                except Exception as exc:
                    logger.warning("Swarm learning failed for trade %d: %s", trade_id, exc)

                # Self-tuner — if market has 5 consecutive losses, tighten or brainwash
                try:
                    from services.lifecycle.market_tuner import tune_if_losing
                    result = tune_if_losing(trade["symbol"])
                    if result.get("action") == "tune":
                        logger.warning("TUNER %s: %d losses, tuning trade management", trade["symbol"], result["streak"])
                    elif result.get("action") == "hold":
                        logger.info("TUNER %s: %d losses, held settings", trade["symbol"], result["streak"])
                except Exception as exc:
                    logger.warning("Tuner failed for trade %d: %s", trade_id, exc)

                # Circuit breaker disabled — SIM-only mode.

                logger.info(
                    "Trade %d CLOSED (%s): %s %s pnl=%.2f%%",
                    trade_id, close_reason, side, trade["symbol"], pnl_pct
                )
            else:
                pnl_dollars = round(stake * pnl_pct / 100.0, 4)
                cursor.execute("""
                    UPDATE trades SET
                        current_price = ?, pnl = ?, pnl_pct = ?, pnl_dollars = ?,
                        peak_pnl_dollars = ?
                    WHERE id = ?
                """, (new_price, round(pnl_pct, 4), round(pnl_pct, 4), pnl_dollars,
                      round(peak_profit, 4), trade_id))
