"""
Data sources — fetches live market data for equity engines only.
Equity: Yahoo Finance 5-minute intraday bars → compute multi-timeframe returns.
"""
from core.logger import logger
from services.data import yahoo_client


def fetch_all_equity_batch(symbols: list) -> dict:
    """
    Fetch latest price data for all equity symbols using Yahoo Finance intraday bars.
    Returns {symbol: {"price": float, "5m": pct, "15m": pct, "30m": pct,
                      "60m": pct, "simulated": False}}.
    """
    if not symbols:
        return {}

    result: dict = {}
    try:
        raw = yahoo_client.get_intraday_ohlc_batch(symbols)
        for sym, data in raw.items():
            if not data:
                continue
            price = data.get("price", 0)
            if not price or price <= 0:
                continue
            result[sym] = {
                "price": price,
                "5m": data.get("5m", 0.0),
                "15m": data.get("15m", 0.0),
                "30m": data.get("30m", 0.0),
                "60m": data.get("60m", 0.0),
                "simulated": False,
            }
        logger.info(
            "fetch_all_equity_batch: got %d/%d symbols (Yahoo)",
            len(result), len(symbols),
        )
        return result
    except Exception as exc:
        logger.warning("fetch_all_equity_batch failed: %s", exc)
        return result
