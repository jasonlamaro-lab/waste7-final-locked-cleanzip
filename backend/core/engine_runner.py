"""
Async engine runner — replaces the threaded background loop.

Pattern (option b, adapted to SQLite):
  - asyncio task started in FastAPI lifespan
  - Each cycle: persist engine_state + append cycle_telemetry row
  - Single-instance is implicit (uvicorn --workers 1)
  - Sync engine work (yfinance, EODHD, SQLite) runs inside asyncio.to_thread()
    so it doesn't block the event loop
  - Crash-isolated: any exception is captured and persisted, then the loop
    backs off and continues
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from core.config import SYSTEM_CYCLE_SECONDS, TRADE_UPDATE_INTERVAL
from core.db import db_cursor
from core.logger import logger

_stopped = False


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _set_engine_state(status: str, last_error: Optional[str] = None,
                      last_cycle_at: Optional[str] = None,
                      last_cycle_seq: Optional[int] = None) -> None:
    fields = ["status = ?"]
    args = [status]
    if last_error is not None or status == "OK":
        fields.append("last_error = ?")
        args.append(last_error)
    if last_cycle_at is not None:
        fields.append("last_cycle_at = ?")
        args.append(last_cycle_at)
    if last_cycle_seq is not None:
        fields.append("last_cycle_seq = ?")
        args.append(last_cycle_seq)
    fields.append("updated_at = CURRENT_TIMESTAMP")
    sql = f"UPDATE engine_state SET {', '.join(fields)} WHERE id = 1"
    with db_cursor() as (_, cur):
        cur.execute(sql, args)


def _append_telemetry(cycle_seq: int, started_at: str, finished_at: str,
                      elapsed: float, status: str,
                      markets_updated: int, symbols_fetched: int,
                      error: Optional[str]) -> None:
    with db_cursor() as (_, cur):
        cur.execute(
            """INSERT INTO cycle_telemetry
               (cycle_seq, started_at, finished_at, elapsed_seconds,
                status, markets_updated, symbols_fetched, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (cycle_seq, started_at, finished_at, elapsed,
             status, markets_updated, symbols_fetched, error),
        )


def _get_cycle_seq() -> int:
    with db_cursor() as (_, cur):
        cur.execute("SELECT last_cycle_seq FROM engine_state WHERE id = 1")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def _run_one_cycle_blocking() -> tuple[int, int]:
    """
    Execute one full engine cycle (sync). Returns (markets_updated, symbols_fetched)
    for telemetry. Runs inside asyncio.to_thread() so blocking I/O doesn't
    starve the event loop.
    """
    from core.system import run_system_cycle, _MASTER_SYMBOLS, STATE
    run_system_cycle()
    markets_updated = (STATE.get("engines", {}).get("equity") or {}).get("markets_updated", 0)
    return markets_updated, len(_MASTER_SYMBOLS or [])


def _run_trade_update_blocking() -> None:
    from services.execution.trade_manager import update_open_trades
    update_open_trades()


async def trade_update_task():
    """Mirror of core.system.trade_update_loop, but cooperative."""
    logger.info("Trade update task started (interval=%ds)", TRADE_UPDATE_INTERVAL)
    while not _stopped:
        try:
            await asyncio.to_thread(_run_trade_update_blocking)
        except Exception as exc:
            logger.warning("trade_update_task error: %s", exc)
        await asyncio.sleep(TRADE_UPDATE_INTERVAL)


async def engine_run_forever():
    """
    Main engine loop. One task instance per process. Crash-isolated.

    Lifecycle:
      1. mark engine_state = RUNNING
      2. wait 10s for server to settle
      3. loop:
         a. record start_ts
         b. call run_system_cycle (off main thread)
         c. write telemetry row + bump cycle_seq
         d. sleep SYSTEM_CYCLE_SECONDS
      4. on any exception: write ERROR telemetry + back off 5s
    """
    logger.info("Engine async task starting (cycle=%ds)", SYSTEM_CYCLE_SECONDS)
    _set_engine_state("STARTING", last_error=None)

    # Boot grace period
    await asyncio.sleep(10)
    _set_engine_state("RUNNING", last_error=None)

    while not _stopped:
        started_at = _utcnow_iso()
        t0 = time.time()
        cycle_seq = _get_cycle_seq() + 1
        status = "OK"
        error_text: Optional[str] = None
        markets_updated = 0
        symbols_fetched = 0
        try:
            markets_updated, symbols_fetched = await asyncio.to_thread(_run_one_cycle_blocking)
        except Exception as exc:
            status = "ERROR"
            error_text = f"{type(exc).__name__}: {exc}"
            logger.exception("Engine cycle #%d failed: %s", cycle_seq, exc)

        # Auto-optimizer — runs every cycle, nudges gates/thresholds based on win rate
        if status == "OK":
            try:
                from services.intelligence.auto_optimizer import run_optimizer
                run_optimizer()
            except Exception as exc:
                logger.debug("Auto-optimizer skipped: %s", exc)

        elapsed = round(time.time() - t0, 3)
        finished_at = _utcnow_iso()

        # Persist telemetry + state
        try:
            _append_telemetry(cycle_seq, started_at, finished_at, elapsed,
                              status, markets_updated, symbols_fetched, error_text)
            _set_engine_state(
                "RUNNING" if status == "OK" else "ERROR",
                last_error=error_text,
                last_cycle_at=finished_at,
                last_cycle_seq=cycle_seq,
            )
        except Exception as exc:
            logger.warning("Engine telemetry write failed: %s", exc)

        # Back off harder on error so we don't hammer broken external deps
        if status == "ERROR":
            await asyncio.sleep(5)
        await asyncio.sleep(SYSTEM_CYCLE_SECONDS)

    _set_engine_state("STOPPED")
    logger.info("Engine async task stopped")


def stop() -> None:
    global _stopped
    _stopped = True


# ---------------------------------------------------------------------------
# Read-side helpers for /api endpoints
# ---------------------------------------------------------------------------

def get_engine_state() -> dict:
    with db_cursor() as (_, cur):
        cur.execute(
            "SELECT last_cycle_at, last_cycle_seq, status, last_error, updated_at "
            "FROM engine_state WHERE id = 1"
        )
        row = cur.fetchone()
        if not row:
            return {}
        return {
            "last_cycle_at":  row[0],
            "last_cycle_seq": row[1],
            "status":         row[2],
            "last_error":     row[3],
            "updated_at":     row[4],
        }


def get_recent_telemetry(limit: int = 50) -> list[dict]:
    with db_cursor() as (_, cur):
        cur.execute(
            "SELECT id, cycle_seq, started_at, finished_at, elapsed_seconds, "
            "       status, markets_updated, symbols_fetched, error "
            "FROM cycle_telemetry ORDER BY id DESC LIMIT ?",
            (int(limit),),
        )
        rows = cur.fetchall()
    return [
        {
            "id":               r[0],
            "cycle_seq":        r[1],
            "started_at":       r[2],
            "finished_at":      r[3],
            "elapsed_seconds":  r[4],
            "status":           r[5],
            "markets_updated":  r[6],
            "symbols_fetched":  r[7],
            "error":            r[8],
        }
        for r in rows
    ]
