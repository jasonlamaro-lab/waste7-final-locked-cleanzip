import sqlite3
import threading
from contextlib import contextmanager
from core.config import DB_PATH

_DB_WRITE_LOCK = threading.RLock()


def _configure_conn(conn: sqlite3.Connection, wal: bool = True) -> sqlite3.Connection:
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def get_conn(row_factory: bool = False):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    if row_factory:
        conn.row_factory = sqlite3.Row
    return _configure_conn(conn, wal=True)


def get_ro_conn(row_factory: bool = True):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    if row_factory:
        conn.row_factory = sqlite3.Row
    return _configure_conn(conn, wal=False)


class LockedWriteConnection:
    """SQLite write connection that serializes writers process-wide.

    Replit deploys were dying from multiple server/engine threads all trying
    to write SQLite at once. This wrapper preserves the old conn.execute() API
    but forces writers to take turns, while read-only dashboard polling remains
    fast through get_ro_conn().
    """
    def __init__(self, row_factory: bool = True):
        self._released = False
        _DB_WRITE_LOCK.acquire()
        try:
            self._conn = get_conn(row_factory=row_factory)
        except Exception:
            _DB_WRITE_LOCK.release()
            raise

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            try:
                self._conn.rollback()
            except Exception:
                pass
        else:
            self._conn.commit()
        self.close()
        return False

    def close(self):
        if self._released:
            return
        try:
            self._conn.close()
        finally:
            self._released = True
            _DB_WRITE_LOCK.release()


def get_rw_conn(row_factory: bool = True):
    return LockedWriteConnection(row_factory=row_factory)


@contextmanager
def db_cursor():
    conn = get_rw_conn(row_factory=False)
    cursor = conn.cursor()
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_setting(key: str, default: str = None) -> str | None:
    """Read a persisted runtime setting from the DB."""
    try:
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default
    except Exception:
        return default


def set_setting(key: str, value: str) -> None:
    """Persist a runtime setting to the DB."""
    with db_cursor() as (_, cursor):
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value)
        )


def load_settings_into_env() -> None:
    """On startup: restore persisted settings into os.environ (platform env vars take priority)."""
    import os
    runtime_keys = [
        "IG_USER", "IG_PASSWORD", "EODHD_API_KEY",
        "TRADE_STYLE", "STOP_LOSS_PCT", "TRAILING_STOP_PCT", "BASE_TRADE_AMOUNT",
    ]
    for key in runtime_keys:
        if os.environ.get(key):
            continue  # platform-set env var wins
        val = get_setting(key)
        if val:
            os.environ[key] = val


def _add_column_if_missing(cursor, table: str, column: str, col_type: str):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def init_db():
    with db_cursor() as (conn, cursor):
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL NOT NULL,
            status TEXT NOT NULL,
            pnl REAL NOT NULL DEFAULT 0,
            reason TEXT,
            stop_loss_price REAL,
            trailing_stop_price REAL,
            peak_price REAL,
            closed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        _add_column_if_missing(cursor, "trades", "stop_loss_price", "REAL")
        _add_column_if_missing(cursor, "trades", "trailing_stop_price", "REAL")
        _add_column_if_missing(cursor, "trades", "peak_price", "REAL")
        _add_column_if_missing(cursor, "trades", "closed_at", "DATETIME")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal TEXT,
            confidence REAL,
            wps REAL,
            alignment INTEGER,
            regime TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            source TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            detail TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kitty (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            balance REAL NOT NULL DEFAULT 10000.0,
            reserved REAL NOT NULL DEFAULT 0.0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("INSERT OR IGNORE INTO kitty (id, balance) VALUES (1, 10000.0)")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_state (
            market TEXT PRIMARY KEY,
            lifecycle TEXT NOT NULL DEFAULT 'SIM',
            win_count INTEGER NOT NULL DEFAULT 0,
            loss_count INTEGER NOT NULL DEFAULT 0,
            total_pnl REAL NOT NULL DEFAULT 0.0,
            profit_factor REAL NOT NULL DEFAULT 0.0,
            win_rate REAL NOT NULL DEFAULT 0.0,
            regime_accuracy REAL NOT NULL DEFAULT 0.0,
            sim_trades INTEGER NOT NULL DEFAULT 0,
            brain_wash_count INTEGER NOT NULL DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS swarm_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_key TEXT NOT NULL,
            flagging_market TEXT NOT NULL,
            outcome TEXT NOT NULL,
            regime TEXT,
            wps_band TEXT,
            vote_count INTEGER NOT NULL DEFAULT 1,
            soft_gate_active INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(pattern_key, flagging_market)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS night_manager_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            old_thresholds TEXT,
            new_thresholds TEXT,
            summary TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kitty_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            amount REAL NOT NULL,
            balance_after REAL NOT NULL,
            market TEXT,
            trade_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Per-cycle engine telemetry — written at the end of each system cycle.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cycle_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_seq        INTEGER NOT NULL,
            started_at       DATETIME NOT NULL,
            finished_at      DATETIME NOT NULL,
            elapsed_seconds  REAL NOT NULL,
            status           TEXT NOT NULL,   -- OK | ERROR
            markets_updated  INTEGER NOT NULL DEFAULT 0,
            symbols_fetched  INTEGER NOT NULL DEFAULT 0,
            error            TEXT
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cycle_telemetry_seq ON cycle_telemetry(cycle_seq DESC)")

        # Engine state singleton (id=1).
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS engine_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_cycle_at    DATETIME,
            last_cycle_seq   INTEGER NOT NULL DEFAULT 0,
            status           TEXT NOT NULL DEFAULT 'IDLE',
            last_error       TEXT,
            updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("INSERT OR IGNORE INTO engine_state (id, status) VALUES (1, 'IDLE')")

        _add_column_if_missing(cursor, "trades", "size", "REAL DEFAULT 2.0")
        _add_column_if_missing(cursor, "trades", "kitty_level", "INTEGER DEFAULT 1")
        _add_column_if_missing(cursor, "trades", "is_sim", "INTEGER DEFAULT 1")
        # Broker-side tracking for LIVE orders (cTrader/Pepperstone)
        _add_column_if_missing(cursor, "trades", "broker_order_id", "TEXT")
        _add_column_if_missing(cursor, "trades", "broker_position_id", "TEXT")
        _add_column_if_missing(cursor, "trades", "broker_fill_price", "REAL")
        _add_column_if_missing(cursor, "trades", "broker_status", "TEXT")
        _add_column_if_missing(cursor, "trades", "broker_error", "TEXT")
        # Dollar-based risk model: track peak P&L in $ for trailing stop
        _add_column_if_missing(cursor, "trades", "peak_pnl_dollars", "REAL DEFAULT 0")
        _add_column_if_missing(cursor, "market_state", "config", "TEXT")
        _add_column_if_missing(cursor, "market_state", "brain_wash_count", "INTEGER DEFAULT 0")
        _add_column_if_missing(cursor, "swarm_patterns", "wins", "INTEGER DEFAULT 0")
        _add_column_if_missing(cursor, "trades", "anchor_symbol", "TEXT")
        # pnl_pct = % return on anchor price move; pnl = dollar return on stake
        # (pnl was historically stored as pnl_pct — pnl_dollars makes it unambiguous)
        _add_column_if_missing(cursor, "trades", "pnl_pct", "REAL DEFAULT 0")
        _add_column_if_missing(cursor, "trades", "pnl_dollars", "REAL DEFAULT 0")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
