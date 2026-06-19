"""
Trading Platform — FastAPI Server
Provides JSON-RPC-compatible endpoints that the dashboard-v61.js frontend calls.
Also runs the trading engine loop in a background thread.
"""
import sys
import os
import time
import asyncio
import threading
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Any

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Ensure imports resolve from /app/backend/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import (
    DB_PATH, ENABLE_BACKGROUND_LOOP,
    BROKER_FEE_PCT
)
from core.db import init_db, get_ro_conn, get_rw_conn
from core.logger import logger

# ── Background trading loop (replaced by async tasks in lifespan) ─────────────
_engine_task = None
_trade_update_task = None


def _background_loop():
    """Legacy thread shim kept for ad-hoc use. The async engine_runner is the
    canonical loop now."""
    logger.info("Background trading loop (legacy thread shim)")
    time.sleep(10)
    try:
        from core.system import start_loop
        start_loop()
    except Exception as exc:
        logger.exception("Background loop crashed: %s", exc)


def _constituent_refresh_loop():
    """Refreshes equity constituents monthly. Runs in background thread."""
    time.sleep(30)  # let the server finish startup
    from engines.equity.constituent_refresh import refresh_all, status
    try:
        st = status()
        stale_markets = [s for s in st if s["refreshed_at"] is None]
        if stale_markets:
            logger.info("Constituent refresh: %d markets stale on boot, running initial refresh", len(stale_markets))
            refresh_all()
    except Exception as exc:
        logger.warning("Initial constituent refresh failed: %s", exc)

    # Monthly cadence — check every 24 hours, refresh if last one was >28 days ago
    while True:
        time.sleep(24 * 3600)
        try:
            from datetime import datetime, timedelta
            st = status()
            now = datetime.utcnow()
            due = []
            for s in st:
                r = s.get("refreshed_at")
                if not r:
                    due.append(s["market"]); continue
                try:
                    last = datetime.fromisoformat(str(r).replace("Z","").split(".")[0])
                    if (now - last) > timedelta(days=28):
                        due.append(s["market"])
                except Exception:
                    due.append(s["market"])
            if due:
                logger.info("Monthly constituent refresh: %d markets due", len(due))
                from engines.equity.constituent_refresh import refresh_market
                for slug in due:
                    refresh_market(slug)
        except Exception as exc:
            logger.warning("Monthly constituent refresh loop error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine_task, _trade_update_task
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized at %s", DB_PATH)

    # Restore persisted runtime settings (credentials, trade style, risk params)
    # into os.environ so all code that reads os.getenv() gets them immediately.
    # Platform-level env vars (set in Replit Secrets / Railway / Render) take priority.
    from core.db import load_settings_into_env
    load_settings_into_env()
    logger.info("Runtime settings loaded into environment")

    # Mode-A governor retired. Auto-Optimizer owns thresholds; Market Tuner owns trade management.

    # Start async engine + trade-update tasks (replaces threaded loops)
    if ENABLE_BACKGROUND_LOOP:
        from core.engine_runner import engine_run_forever, trade_update_task
        _engine_task = asyncio.create_task(engine_run_forever())
        _trade_update_task = asyncio.create_task(trade_update_task())
        logger.info("Engine + trade-update async tasks started")

    # Start monthly constituent refresh scheduler (still a thread — it's a
    # once-a-day cron-style check, no need to convert)
    try:
        threading.Thread(target=_constituent_refresh_loop, daemon=True).start()
        logger.info("Constituent refresh scheduler started")
    except Exception as exc:
        logger.warning("Constituent refresh scheduler failed to start: %s", exc)

    # cTrader broker disconnected — running broker-less while between brokers
    logger.info("Broker connection: DISABLED (cTrader/Pepperstone disconnected)")

    yield

    # Graceful shutdown of async tasks
    logger.info("Server shutting down — stopping engine tasks")
    try:
        from core.engine_runner import stop as engine_stop
        engine_stop()
    except Exception:
        pass
    for t in (_engine_task, _trade_update_task):
        if t and not t.done():
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(title="Trading Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helper: SQLite access to trading.db ───────────────────────────────────────
def _get_ro_conn():
    return get_ro_conn(row_factory=True)


def _get_rw_conn():
    return get_rw_conn(row_factory=True)


# ── JSON-RPC wrapper ──────────────────────────────────────────────────────────
def _wrap_rpc_response(rpc_id: Any, result: Any) -> dict:
    """Wrap result in the superjson/JSON-RPC envelope the dashboard expects."""
    return {
        "json": {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": result
        }
    }


def _parse_rpc_request(body: dict) -> tuple:
    """Parse incoming RPC request, return (id, method, params)."""
    inner = body.get("json", body)
    rpc_id = inner.get("id", 1)
    method = inner.get("method", "")
    params = inner.get("params", [])
    return rpc_id, method, params


# ── RPC HANDLERS ──────────────────────────────────────────────────────────────

def _handle_health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "db": "connected" if os.path.exists(DB_PATH) else "disconnected",
    }


def _handle_get_trades():
    """Return all OPEN/CLOSED/PENDING trades — both LIVE and SIM. Frontend
    filters by `is_sim` flag per row. REJECTED orders excluded (broker noise)."""
    conn = _get_ro_conn()
    try:
        rows = conn.execute("""
            SELECT id, engine, symbol, side, entry_price, current_price,
                   status, pnl, reason, created_at, closed_at,
                   is_sim, size, kitty_level, stop_loss_price,
                   broker_status, broker_position_id, broker_fill_price,
                   peak_pnl_dollars
            FROM trades
            WHERE status IN ('OPEN','CLOSED','PENDING')
            ORDER BY id DESC LIMIT 500
        """).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def _handle_get_market_state():
    conn = _get_ro_conn()
    markets = {}
    lifecycle = {}
    kitty = None
    swarm = None
    last_cycle = None
    equity_count = 0

    try:
        try:
            rows = conn.execute("""
                SELECT market, symbol, signal, confidence, wps, alignment, regime, created_at
                FROM signals
                WHERE id IN (SELECT MAX(id) FROM signals GROUP BY market)
                ORDER BY created_at DESC
            """).fetchall()
            # Pull in-memory timeframes/direction from the live engine STATE
            try:
                from core.system import STATE as _ENGINE_STATE
                _mem = _ENGINE_STATE.get("markets", {}) or {}
            except Exception:
                _mem = {}
            for r in rows:
                entry = {
                    "signal": r["signal"],
                    "confidence": r["confidence"],
                    "wps": r["wps"],
                    "alignment": r["alignment"],
                    "regime": r["regime"],
                    "updated_at": r["created_at"],
                }
                mem = _mem.get(r["market"]) or {}
                if mem.get("timeframes"):
                    entry["timeframes"] = mem["timeframes"]
                    entry["direction"]  = mem.get("direction")
                if mem.get("price"):
                    entry["price"] = mem["price"]
                markets[r["market"]] = entry
        except Exception:
            pass

        try:
            lc_rows = conn.execute("SELECT * FROM market_state ORDER BY market").fetchall()
            for r in lc_rows:
                lifecycle[r["market"]] = dict(r)
                try:
                    import json as _json
                    cfg = _json.loads(r["config"] or "{}")
                    markets.setdefault(r["market"], {})["wps_threshold"] = cfg.get("wps_threshold")
                    markets.setdefault(r["market"], {})["config"] = cfg
                except Exception:
                    pass
        except Exception:
            pass

        # Per-market SIM vs LIVE performance stats (PF and WR), computed from
        # closed trades. Surfaces as lifecycle[market].{pf_sim,wr_sim,pf_live,wr_live}.
        try:
            perf_rows = conn.execute("""
                SELECT symbol,
                       is_sim,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) AS losses,
                       SUM(CASE WHEN pnl > 0 THEN pnl * COALESCE(size,2) / 100 ELSE 0 END) AS gross_win,
                       SUM(CASE WHEN pnl <= 0 THEN ABS(pnl) * COALESCE(size,2) / 100 ELSE 0 END) AS gross_loss,
                       COUNT(*) AS total
                FROM trades
                WHERE engine='equity' AND status='CLOSED'
                GROUP BY symbol, is_sim
            """).fetchall()
            for r in perf_rows:
                mkt = r["symbol"]
                if mkt not in lifecycle:
                    lifecycle[mkt] = {"market": mkt}
                wins = r["wins"] or 0
                losses = r["losses"] or 0
                gw = r["gross_win"] or 0.0
                gl = r["gross_loss"] or 0.0
                total = wins + losses
                wr = (wins / total) if total else 0.0
                pf = (gw / gl) if gl > 0 else (999.0 if gw > 0 else 0.0)
                suffix = "sim" if r["is_sim"] == 1 else "live"
                lifecycle[mkt][f"wins_{suffix}"]    = wins
                lifecycle[mkt][f"losses_{suffix}"]  = losses
                lifecycle[mkt][f"wr_{suffix}"]      = round(wr, 4)
                lifecycle[mkt][f"pf_{suffix}"]      = round(pf, 2)
                lifecycle[mkt][f"trades_{suffix}"]  = total
        except Exception as e:
            logger.warning("market_state perf split failed: %s", e)

        try:
            kitty_row = conn.execute("SELECT balance FROM kitty WHERE id = 1").fetchone()
            balance = float(kitty_row["balance"]) if kitty_row else 10000.0
            # Single-pool philosophy: balance is already net of open stakes.
            # No "reserved" concept. Faceplate reads balance directly.
            kitty = {"balance": balance, "reserved": 0.0, "available": balance}
            # Attach broker_mirror snapshot so the UI kitty panel shows
            # BROKER LIVE / OFFLINE + Pepperstone balance override.
            try:
                from services.execution.ctrader_balance_mirror import get_live_balance_snapshot
                snap = get_live_balance_snapshot()
                if snap.get("account_authorized") and snap.get("balance") is not None:
                    kitty["broker_mirror"] = {
                        "balance":        snap["balance"],
                        "equity":         snap.get("equity"),
                        "used_margin":    snap.get("used_margin"),
                        "free_margin":    snap.get("free_margin"),
                        "margin_level":   snap.get("margin_level"),
                        "unrealized_pnl": snap.get("unrealized_pnl", 0.0),
                        "open_positions": snap.get("open_positions", 0),
                        "currency":       snap.get("currency"),
                        "broker_name":    snap.get("broker_name"),
                        "last_update":    snap.get("last_update"),
                        "connected":      True,
                    }
                    # Broker is source of truth — override the display balance
                    kitty["balance"]   = snap["balance"]
                    kitty["available"] = snap["balance"]
                else:
                    kitty["broker_mirror"] = {"connected": False}
            except Exception:
                pass
        except Exception:
            pass

        try:
            swarm_rows = conn.execute("""
                SELECT pattern_key, SUM(vote_count) as total_votes,
                       MAX(soft_gate_active) as gated,
                       GROUP_CONCAT(DISTINCT flagging_market) as markets
                FROM swarm_patterns GROUP BY pattern_key
                ORDER BY total_votes DESC LIMIT 10
            """).fetchall()
            patterns = [{
                "pattern": r["pattern_key"],
                "votes": r["total_votes"],
                "gated": bool(r["gated"]),
                "markets": r["markets"].split(",") if r["markets"] else [],
            } for r in swarm_rows]
            swarm = {"patterns": patterns, "active_gates": sum(1 for p in patterns if p["gated"])}
        except Exception:
            pass

        try:
            # Live cycle timestamp from in-memory STATE — accurate even when no
            # new trades inserted on the cycle (dedupe blocks etc.)
            from core.system import STATE as _SYS_STATE
            last_cycle = _SYS_STATE.get("last_cycle")
            if not last_cycle:
                cycle_row = conn.execute("SELECT MAX(created_at) as last FROM trades").fetchone()
                if cycle_row and cycle_row["last"]:
                    last_cycle = datetime.fromisoformat(cycle_row["last"]).timestamp()
        except Exception:
            pass

        try:
            equity_count = conn.execute("SELECT COUNT(*) as n FROM signals WHERE created_at >= datetime('now', '-5 minutes')").fetchone()["n"]
        except Exception:
            pass

    finally:
        conn.close()

    # Merge per-market performance split (pf_live, wr_live, pf_sim, wr_sim) onto
    # the faceplate so the UI can read it directly off the market entry.
    for mkt, m_entry in markets.items():
        lc_entry = lifecycle.get(mkt) or {}
        for k in ("pf_live", "wr_live", "pf_sim", "wr_sim",
                  "trades_live", "trades_sim"):
            if k in lc_entry:
                m_entry[k] = lc_entry[k]

    return {
        "markets": markets,
        "lifecycle": lifecycle,
        "kitty": kitty,
        "swarm": swarm,
        "status": "RUNNING",
        "last_cycle": last_cycle,
        "engines": {
            "equity": {"status": "RUNNING" if equity_count > 0 else "QUIET", "count": equity_count},
        },
    }


def _handle_get_stats():
    conn = _get_ro_conn()
    try:
        q = lambda sql: conn.execute(sql).fetchone()
        # ── GLOBAL STATS — LIVE TRADES ONLY ─────────────────────────────────
        # (SIM trades are purely for the swarm/tuner to learn; they never
        # show up in the dashboard's "Wins / Losses / Net / Today" tiles.)
        total  = q("SELECT COUNT(*) as n FROM trades WHERE is_sim = 0")["n"]
        wins   = q("SELECT COUNT(*) as n FROM trades WHERE status='CLOSED' AND is_sim = 0 AND pnl > 0")["n"]
        losses = q("SELECT COUNT(*) as n FROM trades WHERE status='CLOSED' AND is_sim = 0 AND pnl < 0")["n"]
        total_pnl = q("SELECT COALESCE(SUM(size * pnl / 100.0),0) as s FROM trades WHERE status='CLOSED' AND is_sim = 0")["s"]
        today_wins   = q("SELECT COUNT(*) as n FROM trades WHERE status='CLOSED' AND is_sim = 0 AND pnl > 0 AND date(created_at) = date('now')")["n"]
        today_losses = q("SELECT COUNT(*) as n FROM trades WHERE status='CLOSED' AND is_sim = 0 AND pnl < 0 AND date(created_at) = date('now')")["n"]
        today_pnl    = q("SELECT COALESCE(SUM(size * pnl / 100.0),0) as s FROM trades WHERE status='CLOSED' AND is_sim = 0 AND date(created_at) = date('now')")["s"]

        # Live closed count and avg (same as above since we're already LIVE-only)
        live_closed = q("SELECT COUNT(*) as n FROM trades WHERE status='CLOSED' AND is_sim = 0")["n"]
        live_avg = (float(total_pnl) / live_closed) if live_closed > 0 else None

        # Per-market LIVE breakdown
        per_market_rows = conn.execute("""
            SELECT symbol,
                   COUNT(*) as n,
                   COALESCE(SUM(size * pnl / 100.0),0) as total_pnl,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses
            FROM trades WHERE status='CLOSED' AND is_sim = 0
            GROUP BY symbol
        """).fetchall()
        per_market_live = {}
        for r in per_market_rows:
            n  = r["n"] or 0
            tp = float(r["total_pnl"] or 0)
            per_market_live[r["symbol"]] = {
                "count":    n,
                "totalPnl": tp,
                "avgPnl":   (tp / n) if n > 0 else 0.0,
                "wins":     r["wins"] or 0,
                "losses":   r["losses"] or 0,
            }

        # Last cycle timestamp (unix epoch) — for the dashboard countdown
        try:
            from core.system import STATE as _SYS_STATE
            last_cycle_ts = _SYS_STATE.get("last_cycle")
        except Exception:
            last_cycle_ts = None

        return {
            # ALL of these now reflect LIVE-only data
            "total": total, "wins": wins, "losses": losses,
            "totalPnl": float(total_pnl),
            "todayWins": today_wins, "todayLosses": today_losses,
            "todayPnl": float(today_pnl),
            "winRate": round(wins / (wins + losses) * 100) if (wins + losses) > 0 else 0,
            # Duplicate keys for UI backwards-compat
            "liveClosed":         live_closed,
            "liveWins":           wins,
            "liveLosses":         losses,
            "liveTotalPnl":       float(total_pnl),
            "liveTodayPnl":       float(today_pnl),
            "liveAvgPnlPerTrade": live_avg,
            "liveWinRate":        round(wins / (wins + losses) * 100) if (wins + losses) > 0 else 0,
            "perMarketLive":      per_market_live,
            "mode":               "LIVE_ONLY",
            "last_cycle":         last_cycle_ts,
        }
    except Exception:
        return {"total": 0, "wins": 0, "losses": 0, "totalPnl": 0, "todayWins": 0, "todayLosses": 0, "todayPnl": 0, "winRate": 0,
                "liveClosed": 0, "liveWins": 0, "liveLosses": 0, "liveTotalPnl": 0, "liveTodayPnl": 0,
                "liveAvgPnlPerTrade": None, "liveWinRate": 0, "perMarketLive": {}, "mode": "LIVE_ONLY"}
    finally:
        conn.close()


def _handle_get_kitty_summary():
    conn = _get_ro_conn()
    LADDER = [2, 4, 8, 16, 32]
    empty = {"balance": 400, "reserved": 0, "available": 400, "ladder": LADDER, "max_exposure": 62, "history": [], "broker_mirror": None}

    # Pull broker-mirrored snapshot if cTrader connection is live
    broker_snapshot = None
    try:
        from services.execution.ctrader_balance_mirror import get_live_balance_snapshot
        snap = get_live_balance_snapshot()
        if snap.get("account_authorized") and snap.get("balance") is not None:
            broker_snapshot = {
                "balance":        snap["balance"],
                "equity":         snap.get("equity"),
                "used_margin":    snap.get("used_margin"),
                "free_margin":    snap.get("free_margin"),
                "margin_level":   snap.get("margin_level"),
                "unrealized_pnl": snap.get("unrealized_pnl", 0.0),
                "open_positions": snap.get("open_positions", 0),
                "currency":       snap.get("currency"),
                "broker_name":    snap.get("broker_name"),
                "last_update":    snap.get("last_update"),
                "connected":      True,
            }
        else:
            broker_snapshot = {"connected": False, "last_error": snap.get("last_error")}
    except Exception:
        broker_snapshot = None

    try:
        kitty = conn.execute("SELECT balance FROM kitty WHERE id = 1").fetchone()
        history = conn.execute(
            "SELECT event, amount, balance_after, market, created_at FROM kitty_history ORDER BY id DESC LIMIT 10"
        ).fetchall()
        local_balance = float(kitty["balance"]) if kitty else 10000.0

        # Broker is the source of truth when authorised; otherwise fall back to local.
        if broker_snapshot and broker_snapshot.get("connected"):
            displayed = broker_snapshot["balance"]
        else:
            displayed = local_balance

        return {
            "balance":       displayed,
            "local_balance": local_balance,
            "reserved":      0.0,
            "available":     displayed,
            "ladder":        LADDER,
            "max_exposure":  62,
            "history":       [dict(r) for r in history],
            "broker_mirror": broker_snapshot,
        }
    except Exception:
        empty["broker_mirror"] = broker_snapshot
        return empty
    finally:
        conn.close()


def _handle_get_swarm_summary():
    conn = _get_ro_conn()
    try:
        rows = conn.execute("""
            SELECT pattern_key, SUM(vote_count) as total_votes,
                   MAX(soft_gate_active) as gated,
                   GROUP_CONCAT(DISTINCT flagging_market) as markets
            FROM swarm_patterns GROUP BY pattern_key
            ORDER BY total_votes DESC
        """).fetchall()
        patterns = [{
            "pattern": r["pattern_key"], "votes": r["total_votes"],
            "gated": bool(r["gated"]),
            "markets": r["markets"].split(",") if r["markets"] else [],
        } for r in rows]
        return {"patterns": patterns, "active_gates": sum(1 for p in patterns if p["gated"])}
    except Exception:
        return {"patterns": [], "active_gates": 0}
    finally:
        conn.close()


def _handle_get_system_events():
    conn = _get_ro_conn()
    try:
        rows = conn.execute(
            "SELECT id, level, source, message, created_at FROM system_events ORDER BY id DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()

def _parse_optimizer_market(message: str) -> str | None:
    """Auto-optimizer messages are logged as '<market>: ...'. Extract that market."""
    if not message or ":" not in message:
        return None
    market = message.split(":", 1)[0].strip()
    return market or None


def _optimizer_impact(conn, market: str, created_at: str) -> dict:
    """Score what happened after an optimizer change.
    Uses LIVE closed trades after the change. This is not a prediction; it is an audit trail.
    """
    rows = conn.execute(
        """
        SELECT pnl, size
        FROM trades
        WHERE symbol = ? AND status = 'CLOSED' AND is_sim = 0
          AND COALESCE(closed_at, created_at) >= ?
        ORDER BY id ASC
        """,
        (market, created_at),
    ).fetchall()
    wins = sum(1 for r in rows if float(r["pnl"] or 0) > 0)
    losses = sum(1 for r in rows if float(r["pnl"] or 0) < 0)
    gross_win = sum((float(r["size"] or 0) * float(r["pnl"] or 0) / 100.0) for r in rows if float(r["pnl"] or 0) > 0)
    gross_loss = abs(sum((float(r["size"] or 0) * float(r["pnl"] or 0) / 100.0) for r in rows if float(r["pnl"] or 0) < 0))
    net = gross_win - gross_loss
    pf = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    count = wins + losses
    wr = (wins / count * 100.0) if count else 0.0
    if count < 3:
        verdict = "PENDING"
    elif net > 0 and pf >= 1.2:
        verdict = "HELPING"
    elif net < 0 or pf < 1.0:
        verdict = "HURTING"
    else:
        verdict = "MIXED"
    return {
        "trades": count,
        "wins": wins,
        "losses": losses,
        "winRate": round(wr, 1),
        "profitFactor": round(pf, 2) if pf < 999 else 999,
        "netPnl": round(net, 2),
        "verdict": verdict,
    }


def _handle_get_optimizer_audit():
    """Dashboard audit box: last 5 auto-optimizer changes + changes in last 24h.
    Shows whether trades after each change helped or hurt.
    """
    conn = _get_ro_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, level, source, message, created_at
            FROM system_events
            WHERE source = 'auto_optimizer'
            ORDER BY id DESC
            LIMIT 80
            """
        ).fetchall()
        items = []
        for r in rows:
            msg = r["message"] or ""
            market = _parse_optimizer_market(msg)
            impact = _optimizer_impact(conn, market, r["created_at"]) if market else {
                "trades": 0, "wins": 0, "losses": 0, "winRate": 0, "profitFactor": 0, "netPnl": 0, "verdict": "PENDING"
            }
            items.append({
                "id": r["id"],
                "source": r["source"],
                "message": msg,
                "market": market or "—",
                "created_at": r["created_at"],
                "impact": impact,
            })
        since = datetime.utcnow() - timedelta(hours=24)
        last_24h = []
        for item in items:
            try:
                dt = datetime.fromisoformat(str(item["created_at"]).replace("Z", "").split(".")[0])
            except Exception:
                dt = None
            if dt is None or dt >= since:
                last_24h.append(item)
        return {
            "last5": items[:5],
            "last24h": last_24h,
            "count24h": len(last_24h),
            "helping24h": sum(1 for x in last_24h if x["impact"]["verdict"] == "HELPING"),
            "hurting24h": sum(1 for x in last_24h if x["impact"]["verdict"] == "HURTING"),
        }
    except Exception as exc:
        logger.exception("optimizer audit failed: %s", exc)
        return {"last5": [], "last24h": [], "count24h": 0, "helping24h": 0, "hurting24h": 0, "error": str(exc)}
    finally:
        conn.close()


def _handle_reset_market(params):
    market = params[0] if isinstance(params, list) and params else params if isinstance(params, str) else None
    if not market:
        return {"ok": False, "message": "Invalid market"}

    conn = _get_rw_conn()
    try:
        exists = conn.execute("SELECT 1 FROM market_state WHERE market = ?", (market,)).fetchone()
        if not exists:
            conn.execute("INSERT OR IGNORE INTO market_state (market) VALUES (?)", (market,))
        else:
            conn.execute("""
                UPDATE market_state SET
                    lifecycle = 'SIM', win_count = 0, loss_count = 0, total_pnl = 0.0,
                    profit_factor = 0.0, win_rate = 0.0, regime_accuracy = 0.0,
                    sim_trades = 0, brain_wash_count = brain_wash_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE market = ?
            """, (market,))
        conn.execute("INSERT INTO resets (scope, detail) VALUES (?, ?)", (market, "Manual reset via dashboard"))
        conn.execute("INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
                     ("WARN", "dashboard", f"Manual reset: {market} -> SIM"))
        conn.commit()
        return {"ok": True, "message": f"{market} reset to SIM"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
    finally:
        conn.close()


def _handle_run_trading_cycle():
    timestamp = datetime.utcnow().isoformat()
    try:
        from core.system import run_system_cycle
        run_system_cycle()
        return {"ok": True, "status": "cycle complete", "timestamp": timestamp}
    except Exception as e:
        return {"ok": False, "status": f"error: {e}", "timestamp": timestamp}


def _handle_pause_trading(params):
    """Set a specific market or all markets to LIVE or SIM."""
    from core.state import STATE
    STATE["paused"] = True
    logger.info("TRADING PAUSED by user")
    return {"ok": True, "paused": True}


def _handle_resume_trading(params):
    from core.state import STATE
    STATE["paused"] = False
    logger.info("TRADING RESUMED by user")
    return {"ok": True, "paused": False}


def _handle_get_pause_state(params):
    from core.state import STATE
    return {"paused": STATE.get("paused", False)}


def _handle_set_market_live(params):
    """Promote a market to LIVE status manually."""
    market = params[0] if isinstance(params, list) and params else params
    if not market:
        return {"ok": False, "error": "No market specified"}
    conn = _get_rw_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO market_state (market) VALUES (?)", (market,))
        conn.execute(
            "UPDATE market_state SET lifecycle = 'LIVE', updated_at = CURRENT_TIMESTAMP WHERE market = ?",
            (market,)
        )
        conn.execute(
            "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
            ("INFO", "dashboard", f"MANUAL PROMOTION: {market} → LIVE")
        )
        conn.commit()
        logger.info("Market %s manually promoted to LIVE", market)
        return {"ok": True, "market": market, "lifecycle": "LIVE"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _handle_set_market_sim(params):
    """Demote a market back to SIM status manually."""
    market = params[0] if isinstance(params, list) and params else params
    if not market:
        return {"ok": False, "error": "No market specified"}
    conn = _get_rw_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO market_state (market) VALUES (?)", (market,))
        conn.execute(
            "UPDATE market_state SET lifecycle = 'SIM', updated_at = CURRENT_TIMESTAMP WHERE market = ?",
            (market,)
        )
        conn.execute(
            "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
            ("INFO", "dashboard", f"MANUAL DEMOTION: {market} → SIM")
        )
        conn.commit()
        logger.info("Market %s manually demoted to SIM", market)
        return {"ok": True, "market": market, "lifecycle": "SIM"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _handle_get_constituents_status(params):
    try:
        from engines.equity.constituent_refresh import status
        return status()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _handle_refresh_constituents(params):
    """Manually trigger a constituent refresh. Params: {"market": "asx200"} or null for all."""
    p = params
    while isinstance(p, list):
        p = p[0] if p else None
    try:
        from engines.equity.constituent_refresh import refresh_market, refresh_all
        if isinstance(p, dict) and p.get("market"):
            r = refresh_market(p["market"])
            return r
        if isinstance(p, dict) and p.get("priority_only"):
            return refresh_all(priority_only=True)
        return refresh_all()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _handle_set_markets_lifecycle(params):
    """Flip a specific list of markets to a given lifecycle.
    Params: {"symbols": ["BTC-USD","ETH-USD",...], "lifecycle": "LIVE"|"SIM"}
    When a market flips SIM -> LIVE, ALL open SIM trades on that market are
    immediately closed (to avoid mixing SIM and LIVE positions).
    """
    p = params
    while isinstance(p, list):
        p = p[0] if p else {}
    if not isinstance(p, dict):
        return {"ok": False, "error": "invalid params"}
    symbols = p.get("symbols") or []
    lc = p.get("lifecycle")
    if lc not in ("LIVE", "SIM"):
        return {"ok": False, "error": f"invalid lifecycle: {lc}"}
    if not symbols:
        return {"ok": True, "count": 0}

    conn = _get_rw_conn()
    try:
        placeholders = ",".join(["?"] * len(symbols))
        # Ensure rows exist (market might not have traded yet)
        for s in symbols:
            conn.execute("INSERT OR IGNORE INTO market_state (market) VALUES (?)", (s,))
        conn.execute(
            f"UPDATE market_state SET lifecycle = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE market IN ({placeholders})",
            [lc] + list(symbols)
        )

        closed_trades = 0
        if lc == "LIVE":
            # Close any open SIM trades on these markets so LIVE starts clean
            cur = conn.execute(
                f"UPDATE trades SET status='CLOSED', closed_at=CURRENT_TIMESTAMP, "
                f"reason = COALESCE(reason,'') || ' | AUTO_CLOSE_ON_LIVE_FLIP' "
                f"WHERE status='OPEN' AND is_sim=1 AND symbol IN ({placeholders})",
                list(symbols)
            )
            closed_trades = cur.rowcount or 0
            if closed_trades > 0:
                logger.info("SIM→LIVE flip closed %d open SIM trades across %s",
                            closed_trades, ",".join(symbols[:5]))

        count = conn.execute(
            f"SELECT COUNT(*) FROM market_state WHERE lifecycle=? AND market IN ({placeholders})",
            [lc] + list(symbols)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
            ("INFO", "dashboard",
             f"MANUAL: {count} markets → {lc}" + (f" (closed {closed_trades} SIM trades)" if closed_trades else ""))
        )
        conn.commit()
        logger.info("%d markets → %s (from symbol list)", count, lc)
        return {"ok": True, "count": count, "lifecycle": lc, "closed_sim_trades": closed_trades}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _handle_set_all_live(params):
    """Promote ALL markets to LIVE. Also closes all open SIM trades."""
    conn = _get_rw_conn()
    try:
        conn.execute("UPDATE market_state SET lifecycle = 'LIVE', updated_at = CURRENT_TIMESTAMP")
        cur = conn.execute(
            "UPDATE trades SET status='CLOSED', closed_at=CURRENT_TIMESTAMP, "
            "reason = COALESCE(reason,'') || ' | AUTO_CLOSE_ON_LIVE_FLIP' "
            "WHERE status='OPEN' AND is_sim=1"
        )
        closed_trades = cur.rowcount or 0
        conn.execute(
            "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
            ("INFO", "dashboard",
             "MANUAL: ALL markets → LIVE" + (f" (closed {closed_trades} SIM trades)" if closed_trades else ""))
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM market_state").fetchone()[0]
        logger.info("ALL %d markets promoted to LIVE (closed %d SIM trades)", count, closed_trades)
        return {"ok": True, "count": count, "closed_sim_trades": closed_trades}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _handle_set_all_sim(params):
    """Demote ALL markets to SIM."""
    conn = _get_rw_conn()
    try:
        conn.execute("UPDATE market_state SET lifecycle = 'SIM', updated_at = CURRENT_TIMESTAMP")
        conn.execute(
            "INSERT INTO system_events (level, source, message) VALUES (?, ?, ?)",
            ("INFO", "dashboard", "MANUAL: ALL markets → SIM")
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM market_state").fetchone()[0]
        logger.info("ALL %d markets demoted to SIM", count)
        return {"ok": True, "count": count}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _handle_get_risk_params():
    return {
        "stop_loss_pct":    float(os.getenv("STOP_LOSS_PCT", "5.0")),
        "trailing_stop_pct": float(os.getenv("TRAILING_STOP_PCT", "5.0")),
        "base_trade_amount": float(os.getenv("BASE_TRADE_AMOUNT", "2.0")),
    }


def _handle_set_risk_params(params):
    inp = params[0] if isinstance(params, list) and params else params
    if not isinstance(inp, dict):
        return {"ok": False, "error": "Invalid input"}
    try:
        from core.db import set_setting
        if "stop_loss_pct" in inp:
            val = f"{float(inp['stop_loss_pct']):.1f}"
            os.environ["STOP_LOSS_PCT"] = val
            set_setting("STOP_LOSS_PCT", val)
        if "trailing_stop_pct" in inp:
            val = f"{float(inp['trailing_stop_pct']):.1f}"
            os.environ["TRAILING_STOP_PCT"] = val
            set_setting("TRAILING_STOP_PCT", val)
        if "base_trade_amount" in inp:
            val = f"{max(1.0, round(float(inp['base_trade_amount']) * 100) / 100):.2f}"
            os.environ["BASE_TRADE_AMOUNT"] = val
            set_setting("BASE_TRADE_AMOUNT", val)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _handle_close_trade_now(params):
    logger.info("closeTradeNow called with params: %s (type: %s)", params, type(params))
    # Unwrap nested lists
    trade_id = params
    while isinstance(trade_id, list):
        trade_id = trade_id[0] if trade_id else None
    if not isinstance(trade_id, int):
        try:
            trade_id = int(trade_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": f"Invalid trade ID: {params}"}

    conn = _get_rw_conn()
    try:
        trade = conn.execute(
            "SELECT id, status, pnl, size, symbol, is_sim FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if not trade:
            return {"ok": False, "error": f"Trade {trade_id} not found"}
        if trade["status"] != "OPEN":
            return {"ok": False, "error": "Trade is not open"}

        pnl_pct = trade["pnl"] or 0
        stake = trade["size"] or 2.0
        won = pnl_pct > 0

        # Close the trade
        conn.execute(
            "UPDATE trades SET status = 'CLOSED', closed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (trade_id,)
        )

        # Settle P&L to kitty — LIVE TRADES ONLY (SIM never touches real money)
        if not trade["is_sim"]:
            dollar_pnl = stake * pnl_pct / 100.0
            broker_fee = stake * BROKER_FEE_PCT / 100.0
            net_pnl = dollar_pnl - broker_fee

            kitty_row = conn.execute("SELECT balance, reserved FROM kitty WHERE id = 1").fetchone()
            if kitty_row:
                new_balance = round(kitty_row["balance"] + net_pnl, 4)
                new_reserved = max(0, kitty_row["reserved"] - stake)
                conn.execute(
                    "UPDATE kitty SET balance = ?, reserved = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                    (new_balance, new_reserved)
                )
                event = "WIN" if won else "LOSS"
                conn.execute(
                    "INSERT INTO kitty_history (event, amount, balance_after, market, trade_id) VALUES (?, ?, ?, ?, ?)",
                    (event, round(net_pnl, 4), new_balance, trade["symbol"], trade_id)
                )
                if broker_fee > 0:
                    conn.execute(
                        "INSERT INTO kitty_history (event, amount, balance_after, market, trade_id) VALUES (?, ?, ?, ?, ?)",
                        ("FEE", round(-broker_fee, 4), new_balance, trade["symbol"], trade_id)
                    )

        conn.commit()
        return {"ok": True, "pnl": pnl_pct}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()



def _handle_get_engine_state():
    """Return the backend engine singleton state for dashboard/RPC callers."""
    conn = _get_ro_conn()
    try:
        row = conn.execute("SELECT * FROM engine_state WHERE id = 1").fetchone()
        if row:
            return dict(row)
        return {"id": 1, "status": "IDLE", "last_cycle_seq": 0, "last_cycle_at": None, "last_error": None}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
    finally:
        conn.close()


def _handle_get_cycle_telemetry(params=None):
    """Return recent engine cycle telemetry. Kept small so dashboard polling stays cheap."""
    limit = 25
    try:
        inp = params[0] if isinstance(params, list) and params else params
        if isinstance(inp, dict) and inp.get("limit"):
            limit = max(1, min(100, int(inp.get("limit"))))
    except Exception:
        limit = 25
    conn = _get_ro_conn()
    try:
        rows = conn.execute("""
            SELECT id, cycle_seq, started_at, finished_at, elapsed_seconds,
                   status, markets_updated, symbols_fetched, error
            FROM cycle_telemetry
            ORDER BY cycle_seq DESC, id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return {"ok": True, "cycles": [dict(r) for r in rows]}
    except Exception as e:
        return {"ok": False, "error": str(e), "cycles": []}
    finally:
        conn.close()


def _normalise_market_key(market: str) -> str:
    return str(market or "").strip().lower()


def _ensure_market_state_row(conn, market: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO market_state (market, lifecycle, config) VALUES (?, 'SIM', '{}')",
        (market,)
    )


def _load_market_config(conn, market: str) -> dict:
    import json
    row = conn.execute("SELECT config FROM market_state WHERE market = ?", (market,)).fetchone()
    if row and row["config"]:
        try:
            return json.loads(row["config"]) or {}
        except Exception:
            return {}
    return {}


def _save_market_config(conn, market: str, cfg: dict) -> None:
    import json
    _ensure_market_state_row(conn, market)
    conn.execute(
        "UPDATE market_state SET config = ?, updated_at = CURRENT_TIMESTAMP WHERE market = ?",
        (json.dumps(cfg), market)
    )


def _handle_get_gate_settings(params=None):
    """RPC wrapper for global + per-market gate settings.
    Always returns ALL canonical markets so the dropdown is fully populated
    even for markets that have never traded and have no market_state row yet.
    """
    # Must match frontend EQUITY_MARKETS array order
    ALL_MARKET_KEYS = [
        'nasdaq100','sp500','dowjones','tsx','bovespa',
        'ftse100','dax40','cac40','eurostoxx50','aex','ibex35','mib','omxs30','smi',
        'nikkei225','hangseng','csi300','kospi','sensex','twse','set','asx200','nzx50',
        'tadawul','jse',
    ]
    try:
        from core.gates import load_settings
        import json
        market = None
        inp = params[0] if isinstance(params, list) and params else params
        if isinstance(inp, dict):
            market = inp.get("market")
        elif isinstance(inp, str):
            market = inp
        settings = load_settings(_normalise_market_key(market) if market else None)

        # Ensure every canonical market has a DB row so WPS/CONF can be saved
        rw = _get_rw_conn()
        try:
            for mk in ALL_MARKET_KEYS:
                _ensure_market_state_row(rw, mk)
            rw.commit()
        finally:
            rw.close()

        conn = _get_ro_conn()
        try:
            rows = conn.execute("SELECT market, lifecycle, config FROM market_state").fetchall()
            db_map = {}
            for r in rows:
                cfg = {}
                try:
                    cfg = json.loads(r["config"] or "{}") or {}
                except Exception:
                    cfg = {}
                db_map[r["market"]] = {"lifecycle": r["lifecycle"], "config": cfg}
        finally:
            conn.close()

        # Return in canonical order so dropdown matches frontend list
        markets = []
        for mk in ALL_MARKET_KEYS:
            row = db_map.get(mk, {"lifecycle": "SIM", "config": {}})
            markets.append({"market": mk, "lifecycle": row["lifecycle"], "config": row["config"]})
        return {"ok": True, "settings": settings, "markets": markets}
    except Exception as e:
        return {"ok": False, "error": str(e), "settings": {"gates": {}}}


def _handle_set_gate_setting(params):
    """Set a global gate tightness, or a per-market override when market is supplied.

    Manual per-market settings set a manual flag so automation cannot silently fight the user.
    """
    inp = params[0] if isinstance(params, list) and params else params
    if not isinstance(inp, dict):
        return {"ok": False, "error": "Invalid input"}
    gate = str(inp.get("gate", "")).upper().strip()
    if not gate:
        return {"ok": False, "error": "Missing gate"}
    try:
        tightness = float(inp.get("tightness", 0))
    except Exception:
        return {"ok": False, "error": "Invalid tightness"}
    tightness = max(0.0, min(1.0, tightness))
    market = _normalise_market_key(inp.get("market")) if inp.get("market") else None
    try:
        from core.gates import update_gate_setting, load_settings
        if market:
            conn = _get_rw_conn()
            try:
                _ensure_market_state_row(conn, market)
                cfg = _load_market_config(conn, market)
                if gate == "CONF":
                    cfg["manual_conf_override"] = True
                    cfg["manual_gate_CONF"] = True
                if gate == "WPS":
                    cfg["manual_wps_override"] = True
                    cfg["manual_gate_WPS"] = True
                _save_market_config(conn, market, cfg)
                conn.commit()
            finally:
                conn.close()
        settings = update_gate_setting(gate, tightness=tightness, range_=inp.get("range"), market=market)
        return {"ok": True, "gate": gate, "market": market, "settings": settings}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _handle_set_market_wps_threshold(params):
    """Set per-market WPS threshold and mark it as manual so auto systems do not overwrite it."""
    inp = params[0] if isinstance(params, list) and params else params
    if not isinstance(inp, dict):
        return {"ok": False, "error": "Invalid input"}
    market = _normalise_market_key(inp.get("market"))
    if not market:
        return {"ok": False, "error": "Missing market"}
    try:
        threshold = round(float(inp.get("threshold")), 1)
    except Exception:
        return {"ok": False, "error": "Invalid threshold"}
    threshold = max(0.0, min(100.0, threshold))
    conn = _get_rw_conn()
    try:
        _ensure_market_state_row(conn, market)
        cfg = _load_market_config(conn, market)
        cfg["wps_threshold"] = threshold
        cfg["manual_wps_override"] = True
        cfg["manual_gate_WPS"] = True
        _save_market_config(conn, market, cfg)
        conn.commit()
        return {"ok": True, "market": market, "wps_threshold": threshold, "manual_override": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()

def _handle_get_mode_a_status():
    return {
        "retired": True,
        "message": "Mode-A retired. Auto-Optimizer owns WPS/CONF gates; Market Tuner owns SL/TS/cooldown only.",
        "markets": {},
    }


def _handle_get_mode_a_history():
    return []


# ── Route map ─────────────────────────────────────────────────────────────────
RPC_HANDLERS = {
    "health": lambda p: _handle_health(),
    "getTrades": lambda p: _handle_get_trades(),
    "getMarketState": lambda p: _handle_get_market_state(),
    "getStats": lambda p: _handle_get_stats(),
    "getKittySummary": lambda p: _handle_get_kitty_summary(),
    "getSwarmSummary": lambda p: _handle_get_swarm_summary(),
    "getSystemEvents": lambda p: _handle_get_system_events(),
    "getOptimizerAudit": lambda p: _handle_get_optimizer_audit(),
    "getModeAStatus": lambda p: _handle_get_mode_a_status(),
    "getModeAHistory": lambda p: _handle_get_mode_a_history(),
    "getEngineState": lambda p: _handle_get_engine_state(),
    "getCycleTelemetry": lambda p: _handle_get_cycle_telemetry(p),
    "resetMarket": _handle_reset_market,
    "runTradingCycle": lambda p: _handle_run_trading_cycle(),
    "pauseTrading": _handle_pause_trading,
    "resumeTrading": _handle_resume_trading,
    "getPauseState": _handle_get_pause_state,
    "setMarketLive": _handle_set_market_live,
    "setMarketSim": _handle_set_market_sim,
    "setAllLive": _handle_set_all_live,
    "setAllSim": _handle_set_all_sim,
    "setMarketsLifecycle": _handle_set_markets_lifecycle,
    "getConstituentsStatus": _handle_get_constituents_status,
    "refreshConstituents": _handle_refresh_constituents,
    "getRiskParams": lambda p: _handle_get_risk_params(),
    "getGateSettings": _handle_get_gate_settings,
    "setGateSetting": _handle_set_gate_setting,
    "setMarketWpsThreshold": _handle_set_market_wps_threshold,
    "setRiskParams": _handle_set_risk_params,
    "closeTradeNow": _handle_close_trade_now,
}


# ── Generic RPC endpoint ─────────────────────────────────────────────────────
@app.post("/api/{method}")
async def rpc_endpoint(method: str, request: Request):
    """Handle all RPC calls from the dashboard."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    rpc_id, _, params = _parse_rpc_request(body)

    handler = RPC_HANDLERS.get(method)
    if not handler:
        return _wrap_rpc_response(rpc_id, {"error": f"Unknown method: {method}"})

    try:
        result = handler(params)
        return _wrap_rpc_response(rpc_id, result)
    except Exception as exc:
        logger.exception("RPC %s failed: %s", method, exc)
        return _wrap_rpc_response(rpc_id, {"error": str(exc)})


# ── cTrader OAuth callback ────────────────────────────────────────────────────
@app.get("/api/ctrader/callback")
async def ctrader_callback(code: str = None, error: str = None):
    from fastapi.responses import HTMLResponse
    if error:
        html = f"""<!doctype html><html><head><title>Broker Auth Failed</title><style>body{{background:#0a0a0a;color:#ef4444;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column;gap:18px;}}h1{{font-size:24px;}}p{{color:#ccc;font-size:14px;}}</style></head><body><h1>✗ Auth Failed</h1><p>{error}</p><p style='color:#666;font-size:12px;'>You can close this window.</p></body></html>"""
        return HTMLResponse(content=html, status_code=400)
    if not code:
        return HTMLResponse(content="<h1>No code provided</h1>", status_code=400)
    try:
        from services.execution.ctrader_client import exchange_code
        result = await exchange_code(code)
        if result.get("success"):
            html = """<!doctype html><html><head><title>Broker Connected</title><style>body{background:#0a0a0a;color:#22c55e;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column;gap:18px;}h1{font-size:32px;text-shadow:0 0 24px #22c55e80;}p{color:#ccc;font-size:14px;}</style></head><body><h1>✓ BROKER CONNECTED</h1><p>Pepperstone live trading ready.</p><p style="color:#666;font-size:12px;">This window will close automatically.</p><script>setTimeout(()=>{try{if(window.opener)window.opener.postMessage('broker-connected','*');window.close();}catch(e){}}, 1500);</script></body></html>"""
            return HTMLResponse(content=html)
        else:
            err = result.get("error", "Unknown error")
            html = f"""<!doctype html><html><head><title>Broker Auth Failed</title><style>body{{background:#0a0a0a;color:#ef4444;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column;gap:18px;}}h1{{font-size:24px;}}p{{color:#ccc;font-size:14px;}}</style></head><body><h1>✗ Auth Failed</h1><p>{err}</p></body></html>"""
            return HTMLResponse(content=html, status_code=400)
    except Exception as exc:
        return HTMLResponse(content=f"<h1>Error: {exc}</h1>", status_code=500)


@app.get("/api/ig/status")
async def ig_status():
    """IG Markets broker status."""
    from services.execution import ig_broker
    return ig_broker.get_status()


@app.post("/api/ig/connect")
async def ig_connect():
    """POST /session against IG Markets DEMO/LIVE and persist tokens."""
    from services.execution import ig_broker
    return ig_broker.connect()


@app.get("/api/ig/accounts")
async def ig_accounts():
    """Health-check the IG session by hitting /accounts."""
    from services.execution import ig_broker
    res = ig_broker.fetch_accounts()
    return res or {"error": "no session", "connected": False}


@app.get("/api/ig/positions")
async def ig_positions():
    from services.execution import ig_broker
    positions = ig_broker.fetch_positions()
    return {"positions": positions or [], "count": len(positions or [])}


@app.get("/api/ig/search")
async def ig_search(term: str = "FTSE"):
    """Search IG markets to find correct epics."""
    import urllib.parse
    from services.execution import ig_broker
    if not ig_broker._state["connected"]:
        ig_broker.connect()
    url = f"{ig_broker._base_url()}/markets?searchTerm={urllib.parse.quote(term)}"
    try:
        r = requests.get(url, headers=ig_broker._headers(version="1"), timeout=15)
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code, "body": r.text[:400]}
        markets = (r.json() or {}).get("markets", [])
        return {"ok": True, "count": len(markets), "markets": [
            {"epic": m.get("epic"), "name": m.get("instrumentName"),
             "type": m.get("instrumentType"), "expiry": m.get("expiry"),
             "status": m.get("marketStatus"), "bid": m.get("bid"), "offer": m.get("offer")}
            for m in markets[:20]
        ]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/ig/test-order")
@app.post("/api/ig/test-order")
async def ig_test_order(market: str = "ftse100", side: str = "BUY", stake: float = 50.0):
    """Fire a SINGLE market order to IG demo. Use this before flipping
    auto-execution on. Returns the IG deal reference + confirm body."""
    import time
    from services.execution import ig_broker
    result = ig_broker.submit_market_order(market, side, stake)
    if not result.get("ok"):
        return {"ok": False, "stage": "submit", **result}
    deal_ref = result.get("deal_reference")
    # IG fills asynchronously — poll /confirms to get the dealId + outcome
    time.sleep(1.5)
    try:
        r = requests.get(
            f"{ig_broker._base_url()}/confirms/{deal_ref}",
            headers=ig_broker._headers(version="1"),
            timeout=10,
        )
        confirm = r.json() if r.status_code == 200 else {"http": r.status_code, "body": r.text[:300]}
    except Exception as exc:
        confirm = {"error": str(exc)}
    return {"ok": True, "deal_reference": deal_ref, "confirm": confirm}




@app.get("/api/ctrader/auth-url")
async def ctrader_auth_url():
    from services.execution.ctrader_client import get_auth_url
    return {"url": get_auth_url()}


@app.get("/api/ctrader/test-order")
async def test_live_order(symbol: str = "BTC-USD", side: str = "BUY", volume: int = 1):
    """Debug-only: fire a single test order to verify end-to-end LIVE execution."""
    from services.execution.ctrader_balance_mirror import (
        send_live_order, get_live_balance_snapshot, _SYMBOL_MAP, get_recent_broker_events,
    )
    import time
    snap = get_live_balance_snapshot()
    result = send_live_order(symbol, side, volume, 0, trade_id=0)
    # Wait briefly so the ExecutionEvent can be observed in the same response
    time.sleep(2.0)
    return {
        "mirror": {
            "connected":        snap.get("connected"),
            "authorised":       snap.get("account_authorized"),
            "balance":          snap.get("balance"),
            "symbols_loaded":   len(_SYMBOL_MAP),
        },
        "order_result": result,
        "recent_events": get_recent_broker_events(20),
    }


@app.get("/api/ctrader/events")
async def ctrader_events(limit: int = 50):
    """Return recent broker-side events (orders sent, fills, rejections)."""
    from services.execution.ctrader_balance_mirror import (
        get_recent_broker_events, get_symbol_cooldowns, get_symbol_details_snapshot,
    )
    return {
        "events":     get_recent_broker_events(limit),
        "cooldowns":  get_symbol_cooldowns(),
        "symbol_details": get_symbol_details_snapshot(),
    }


@app.post("/api/ctrader/clear-cooldown")
async def ctrader_clear_cooldown(symbol: str = None):
    """Flush broker cooldowns (all, or a single symbol)."""
    from services.execution.ctrader_balance_mirror import clear_symbol_cooldown, get_symbol_cooldowns
    clear_symbol_cooldown(symbol)
    return {"ok": True, "cooldowns": get_symbol_cooldowns()}


@app.post("/api/ctrader/close-position")
async def ctrader_close_position(position_id: int, volume: int = 0):
    """Close a Pepperstone position directly by broker position id."""
    from services.execution.ctrader_balance_mirror import close_live_position
    return close_live_position(position_id, volume)


@app.get("/api/ctrader/status")
async def ctrader_status():
    from services.execution.ctrader_client import get_status
    return get_status()


@app.get("/api/notifications/status")
async def notif_status():
    from services.notifications.notifier import status as n_status
    return n_status()


@app.post("/api/notifications/test")
async def notif_test():
    from services.notifications.notifier import send as n_send, status as n_status
    s = n_status()
    if not s["sms_enabled"] and not s["email_enabled"]:
        return {"ok": False, "error": "No channels enabled. Add TWILIO_* and/or RESEND_* to .env"}
    n_send(subject="Test alert", body="This is a test notification from the Trading Platform.", event_key=None)
    return {"ok": True, "status": s}


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/gates/settings")
async def gates_get_settings(market: str = None):
    """Get gate settings. Pass ?market=asx200 to see that market's effective settings."""
    from core.gates import load_settings
    return load_settings(market)


@app.post("/api/gates/settings")
async def gates_update_settings(request: Request):
    """Update global gate settings (applies to all markets that haven't been individually tuned)."""
    body = await request.json()
    market = body.get("market")   # optional — if set, updates per-market override
    from core.gates import update_gate_setting
    results = {}
    for gate_name, cfg in body.get("gates", {}).items():
        try:
            update_gate_setting(
                gate_name,
                tightness=cfg.get("tightness", 0.5),
                range_=cfg.get("range"),
                market=market,
            )
            results[gate_name] = "updated"
        except KeyError as exc:
            results[gate_name] = f"error: {exc}"
    from core.gates import load_settings
    return {"updated": results, "settings": load_settings(market)}


@app.post("/api/gates/{gate_name}")
async def gates_update_one(gate_name: str, request: Request):
    body = await request.json()
    market = body.get("market")   # optional per-market override
    from core.gates import update_gate_setting
    try:
        settings = update_gate_setting(
            gate_name,
            tightness=float(body.get("tightness", 0.5)),
            range_=body.get("range"),
            market=market,
        )
        return {"gate": gate_name.upper(), "settings": settings}
    except KeyError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/gates/status")
async def gates_status():
    """
    Returns the current gate evaluation against live market state,
    including WHY each gate is blocking and WHAT needs to change to open it.
    """
    from core.gates import GateContext, run_gates, load_settings, _GATE_ORDER
    from core.config import MAX_CONCURRENT_TRADES, STOP_LOSS_PCT, TRAILING_STOP_PCT
    from core.state import STATE
    from core.db import db_cursor

    # Build a representative context from current system state
    open_trades = 0
    daily_loss_pct = 0.0
    try:
        with db_cursor() as (_, cur):
            cur.execute("SELECT COUNT(*) FROM trades WHERE status IN ('OPEN','PENDING')")
            open_trades = int(cur.fetchone()[0])
            cur.execute(
                "SELECT COALESCE(SUM(pnl),0) FROM trades WHERE status='CLOSED' AND date(closed_at)=date('now') AND pnl<0"
            )
            loss = abs(float(cur.fetchone()[0]))
            cur.execute("SELECT balance FROM kitty WHERE id=1")
            row = cur.fetchone()
            bal = float(row[0]) if row else 10000.0
            daily_loss_pct = (loss / bal * 100) if bal > 0 else 0.0
    except Exception:
        pass

    # Use best available market data for WPS/alignment/TF context
    markets = STATE.get("markets") or {}
    best_wps, best_conf, best_align = 0.0, 0.0, 0
    best_tfs = {}
    for mkt in markets.values():
        if abs(mkt.get("wps", 0)) > abs(best_wps):
            best_wps = mkt.get("wps", 0)
            best_conf = mkt.get("confidence", 0)
            best_align = mkt.get("alignment", 0)
            for tf_info in mkt.get("timeframes", []):
                d = tf_info.get("dir", "NEUTRAL")
                best_tfs[tf_info["tf"]] = 1 if d == "BUY" else (-1 if d == "SELL" else 0)

    ctx = GateContext(
        timeframes=best_tfs,
        wps=best_wps,
        confidence=best_conf,
        regime=next((m.get("regime","NEUTRAL") for m in markets.values() if m.get("signal")), "NEUTRAL"),
        alignment=best_align,
        api_ok=True,
        data_feed_ok=True,
        latency_ms=0.0,
        open_trade_count=open_trades,
        max_concurrent=MAX_CONCURRENT_TRADES,
        stop_loss_pct=STOP_LOSS_PCT,
        trailing_stop_pct=TRAILING_STOP_PCT,
        daily_loss_pct=daily_loss_pct,
        daily_loss_limit_pct=10.0,
    )

    settings = load_settings()
    pipeline = run_gates(ctx, settings)

    gate_diagnostics = []
    for result in pipeline.results:
        gate_name = result.gate
        # Compute proximity pct: how close is the actual value to passing?
        pct = 100 if result.passed else 0
        value_str = ""
        threshold_str = ""
        what_needed = ""

        d = result.detail
        if gate_name == "TIME4":
            required = d.get("required", 2)
            actual = max(
                [v for v in (best_tfs.values() or [0])].count(1),
                [v for v in (best_tfs.values() or [0])].count(-1),
            ) if best_tfs else 0
            pct = min(100, int(actual / required * 100)) if required else 100
            value_str = f"{actual}/4 aligned"
            threshold_str = f"{required}/4 required"
            what_needed = f"Need {required - actual} more timeframe(s) to agree" if actual < required else ""
        elif gate_name == "WPS":
            threshold = d.get("required", 45.0)
            actual = abs(best_wps)
            pct = min(100, int(actual / threshold * 100)) if threshold else 100
            value_str = f"|WPS| {actual:.1f}"
            threshold_str = f"need {threshold:.1f}"
            what_needed = f"|WPS| must rise {threshold - actual:.1f} more pts" if actual < threshold else ""
        elif gate_name == "CONF":
            threshold = d.get("required", 0.20)
            actual = best_conf
            pct = min(100, int(actual / threshold * 100)) if threshold else 100
            value_str = f"CONF {actual:.3f}"
            threshold_str = f"need {threshold:.3f}"
            what_needed = f"Confidence must rise {threshold - actual:.3f}" if actual < threshold else ""
        elif gate_name == "TRENDING":
            pct = 100 if result.passed else min(80, int(abs(best_align) / 2 * 100))
            value_str = f"alignment {best_align}"
            what_needed = result.reason if not result.passed else ""
        elif gate_name == "RISK":
            pct = 100 if result.passed else 50
            what_needed = result.reason if not result.passed else ""
        elif gate_name == "HLTH":
            pct = 100 if result.passed else 0
            what_needed = result.reason if not result.passed else ""

        gate_diagnostics.append({
            "gate":        gate_name,
            "status":      result.status,
            "passed":      result.passed,
            "reason":      result.reason,
            "value":       value_str or str(d),
            "threshold":   threshold_str,
            "pct":         pct,            # 0–100: how close to passing
            "what_needed": what_needed,    # plain-English fix
            "detail":      d,
        })

    return {
        "passed": pipeline.passed,
        "failed_at": pipeline.failed_at,
        "summary": pipeline.summary(),
        "broker_mode": "SIM",   # LIVE execution disabled — platform proving phase
        "gates": gate_diagnostics,
        "context": {
            "best_wps": best_wps,
            "best_conf": best_conf,
            "best_align": best_align,
            "open_trades": open_trades,
            "daily_loss_pct": round(daily_loss_pct, 2),
        },
    }


@app.get("/api/markets/hours")
async def market_hours():
    """Returns open/closed status and session times for all markets."""
    from engines.equity.market_hours import get_all_hours
    return get_all_hours()


@app.get("/api/trade-style")
async def trade_style_get():
    """Returns all trade styles and which is currently active."""
    from core.trade_style import all_styles, get_style
    return {"active": get_style(), "styles": all_styles()}


@app.post("/api/trade-style")
async def trade_style_set(request: Request):
    """Switch TRADE_STYLE by writing to .env. Takes effect next cycle."""
    body = await request.json()
    style = body.get("style", "SWING").upper()
    from core.trade_style import STYLES
    if style not in STYLES:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown style: {style}. Choose SCALP, SWING or HOLD")
    from core.db import set_setting
    os.environ["TRADE_STYLE"] = style
    set_setting("TRADE_STYLE", style)
    from core.trade_style import all_styles, get_style
    return {"set": style, "active": get_style(), "styles": all_styles()}


@app.get("/api/markets/frequency")
async def market_trade_frequency():
    """Trade frequency per market — all-time, last 30d, last 7d, last 24h."""
    from core.db import db_cursor
    result = {}
    try:
        with db_cursor() as (_, cur):
            cur.execute("""
                SELECT
                    symbol,
                    COUNT(*) AS total,
                    SUM(CASE WHEN date(created_at) >= date('now','-7 days')  THEN 1 ELSE 0 END) AS last_7d,
                    SUM(CASE WHEN date(created_at) >= date('now','-1 days')  THEN 1 ELSE 0 END) AS last_24h,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losses,
                    ROUND(SUM(pnl), 2) AS total_pnl,
                    ROUND(AVG(pnl), 2) AS avg_pnl,
                    MAX(created_at) AS last_trade_at
                FROM trades
                WHERE engine = 'equity'
                GROUP BY symbol
                ORDER BY total DESC
            """)
            rows = cur.fetchall()
            for r in rows:
                sym, total, d7, d1, wins, losses, tpnl, apnl, last_at = r
                wr = round(wins / total * 100, 1) if total else 0
                result[sym] = {
                    "symbol":       sym,
                    "total":        total,
                    "last_7d":      d7 or 0,
                    "last_24h":     d1 or 0,
                    "wins":         wins or 0,
                    "losses":       losses or 0,
                    "win_rate":     wr,
                    "total_pnl":    tpnl or 0,
                    "avg_pnl":      apnl or 0,
                    "last_trade_at": last_at,
                }
    except Exception as exc:
        return {"error": str(exc)}

    # Annotate each market with its current loss cooldown status
    try:
        from core.pipeline import _loss_cooldown_active
        for sym in result:
            active, mins = _loss_cooldown_active(sym)
            result[sym]["cooldown_active"] = active
            result[sym]["cooldown_mins_remaining"] = mins if active else 0
    except Exception:
        pass

    return {"markets": result, "count": len(result)}


@app.post("/api/settings/credentials")
async def save_credentials(request: Request):
    """Save IG and EODHD credentials to the settings DB. Only updates non-empty fields."""
    from fastapi import HTTPException
    body = await request.json()
    ig_user     = (body.get("ig_user") or "").strip()
    ig_password = (body.get("ig_password") or "").strip()
    eodhd_key   = (body.get("eodhd_api_key") or "").strip()

    if not any([ig_user, ig_password, eodhd_key]):
        raise HTTPException(status_code=400, detail="No credentials provided")

    from core.db import set_setting
    updates = {}
    if ig_user:     updates["IG_USER"]      = ig_user
    if ig_password: updates["IG_PASSWORD"]   = ig_password
    if eodhd_key:   updates["EODHD_API_KEY"] = eodhd_key

    for key, val in updates.items():
        os.environ[key] = val
        set_setting(key, val)

    logger.info("Credentials updated via settings panel: %s", list(updates.keys()))
    return {"saved": list(updates.keys()), "ok": True}


@app.get("/api/data-quality")
async def data_quality():
    """Live price feed quality — coverage % and staleness per market."""
    try:
        from services.data.quality_monitor import get_quality_report, alert_stale_markets
        return {
            "markets": get_quality_report(),
            "stale_alerts": alert_stale_markets(),
            "overall_ok": len(alert_stale_markets()) == 0,
        }
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/health")
async def health():
    return _handle_health()


# ── Serve frontend (must be last — API routes take precedence) ────────────────
from fastapi.staticfiles import StaticFiles

_FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'public'
)
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


@app.middleware("http")
async def _no_cache_frontend(request, call_next):
    response = await call_next(request)
    ctype = response.headers.get("content-type", "")
    if ("text/html" in ctype) or ("javascript" in ctype):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        if "etag" in response.headers:
            del response.headers["etag"]
        if "last-modified" in response.headers:
            del response.headers["last-modified"]
    return response
