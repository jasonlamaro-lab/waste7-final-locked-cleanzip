"""
Pepperstone Broker — LIVE order execution via cTrader Open API (Protobuf TCP).

All orders route through the already-authenticated TCP connection in
`ctrader_balance_mirror`. No REST endpoints are used — cTrader's Open API
does not provide one for trading.
"""
from core.logger import logger
from core.db import db_cursor


def _volume_for(symbol: str, price: float, dollar_size: float) -> int:
    """
    Translate our dollar trade size into cTrader's volume unit (1/100 lot for
    crypto, 1/100_000 lot for forex/indices). We use a conservative floor of
    1 cent per pip for now — Pepperstone will reject if below minimum.

    For indices/equity CFDs on Pepperstone, 1 contract ≈ $1 per point.
    For crypto CFDs, 1 unit = 1 coin; min typically 0.01.

    Rule:
      crypto  → volume = max(1, int(dollar_size / price * 100))
                (units of 1/100 of a coin)
      indices → volume = max(100, int(dollar_size * 100 / price))
                (hundredths of a contract; min 100 = 0.01)
      default → same as indices
    """
    if price <= 0:
        return 0
    if symbol.endswith("-USD"):
        # Crypto: 0.01 coin units, min 1
        return max(1, int(dollar_size / price * 100))
    # Indices / equity CFDs: 0.01 lot minimum
    return max(100, int(dollar_size * 100 / max(price, 1)))


def place_real_order(symbol: str, side: str, price: float,
                     stop_loss: float, trailing_stop_pct: float = 0.0,
                     dollar_size: float = 10.0, trade_id: int = 0):
    """
    Place a LIVE market order on Pepperstone via the Protobuf TCP client.
    Returns {'ok': True, ...} on success, {'ok': False, 'error': '...'} on failure.
    """
    try:
        from services.execution.ctrader_balance_mirror import send_live_order
    except Exception as exc:
        logger.warning("Broker mirror unavailable: %s", exc)
        return {"ok": False, "error": "mirror unavailable"}

    volume = _volume_for(symbol, price, dollar_size)
    if volume <= 0:
        return {"ok": False, "error": f"invalid volume for {symbol} @ {price}"}

    result = send_live_order(symbol_name=symbol, side=side, volume=volume,
                             stop_loss_price=float(stop_loss or 0),
                             trade_id=trade_id)

    if result.get("ok"):
        logger.info("LIVE ORDER SENT: %s %s @ %.4f SL=%.4f vol=%d broker=%s symbol_id=%s",
                    side, symbol, price, stop_loss or 0, volume,
                    result.get("broker_name"), result.get("symbol_id"))
        try:
            with db_cursor() as (conn, cursor):
                cursor.execute(
                    "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
                    ("INFO", "broker",
                     f"LIVE order sent: {side} {symbol} @ {price:.4f} "
                     f"(broker={result.get('broker_name')} vol={volume})")
                )
        except Exception:
            pass
        return {
            "ok": True,
            "engine": "live",
            "symbol": symbol,
            "side": side,
            "price": price,
            "status": "OPEN",
            "broker_response": result,
        }

    err = result.get("error", "unknown")
    logger.error("LIVE ORDER REJECTED: %s %s — %s", side, symbol, err)
    try:
        with db_cursor() as (conn, cursor):
            cursor.execute(
                "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
                ("ERROR", "broker",
                 f"LIVE order rejected: {side} {symbol} — {err}")
            )
    except Exception:
        pass
    return {"ok": False, "error": err}
