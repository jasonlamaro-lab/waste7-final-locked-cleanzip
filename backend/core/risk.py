from core.config import MAX_CONCURRENT_TRADES
from core.db import db_cursor


def open_trade_count() -> int:
    with db_cursor() as (conn, cursor):
        cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'OPEN'")
        return int(cursor.fetchone()[0])


def can_trade() -> bool:
    return open_trade_count() < MAX_CONCURRENT_TRADES
