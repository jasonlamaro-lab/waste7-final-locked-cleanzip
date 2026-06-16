---
name: Trading app (Emergent import) setup
description: How this FastAPI + static-dashboard trading app runs on Replit, how to install its deps, and how its live data feed + dashboard wiring work
---

# Trading Engine app — running on Replit

This repo was imported from Emergent (separate `backend/` FastAPI + `frontend/` CRA/craco), but the React app is a no-op (`App.js` renders null). The real UI is a **static dashboard**: `frontend/public/index.html` + `frontend/public/public/dashboard-v61.js`, which call `/api/...` relative URLs.

**Single-process model:** `backend/server.py` mounts the static frontend at `/` (StaticFiles) AND serves all `/api/*` routes. So one FastAPI server serves everything — no separate frontend dev server needed. It reads `PORT` env (falls back to `API_PORT`/8001).

**Workflow:** one webview workflow on port 5000: `cd backend && PORT=5000 uvicorn server:app --host 0.0.0.0 --port 5000`.

**Dependencies:** `requirements.txt` is huge and mostly unused (AI/cloud SDKs). The app only actually imports: `fastapi`, `uvicorn`, `python-dotenv`, `pytz`, `requests`, `ctrader_open_api` (pulls in `twisted`/`protobuf`). Plus `starlette`, `python-multipart`.
- `emergentintegrations==0.1.0` is NOT on PyPI (Emergent-only) — removed from requirements; never imported in code.
- `litellm==1.80.0` is firewall-blocked (HTTP 403) — unused, so skip it.
- `yfinance`/`pandas`/`numpy` are listed but were intentionally NOT installed — the batch fetch was rewired to EODHD (see below), so they're dead deps now.
**Why:** installing the full pinned requirements.txt fails on those; installing only the real subset works.

# Live data feed — EODHD, not yfinance

**The per-cycle batch price fetch uses EODHD intraday bars, NOT yfinance.** `core/data_sources.py::fetch_all_equity_batch(symbols)` calls `services/data/eodhd_client.get_intraday_ohlc()` for each of ~193 constituents in a `ThreadPoolExecutor` and returns `{symbol: {price, "5m","15m","30m","60m", simulated:False}}`. The EODHD `_SESSION` has an HTTPAdapter with pool 20 to match the worker count.

**Why the EODHD key alone did nothing originally:** the old batch fetch was yfinance-only (and yfinance wasn't installed) → returned `{}` → quality monitor reported 0% coverage for all markets regardless of the key. EODHD was only a per-anchor fallback in `core/system.py`.

**Coverage gotcha:** `services/data/quality_monitor.py` counts a symbol as *valid* only if `price>0` AND not all of 5m/15m/30m/60m are exactly 0.0 (all-zero → counted "stale"). So the feed must supply real intraday timeframe returns, not just spot price.

**EODHD plan-tier limits:** intraday is unavailable for some exchanges on the current tier — those markets stay stale (observed: nikkei225/Tokyo, mib/Milan, nzx50, set/Thailand, sometimes sensex). Index spot works but per-constituent intraday does not. This is a data-plan limit, not a code bug.

# Dashboard wiring — static grid vs renderMarkets (NON-OBVIOUS)

`index.html` ships a **static** AMERICAS/EUROPE/… market grid whose value spans use ids `wps-val-<key>`, `conf-<key>`, `align-<key>`, `sig-<key>`, `regime-<key>`, `mom-<key>`, `wps-bar[-neg]-<key>` (20 markets). **`dashboard-v61.js::renderMarkets()` does NOT update those** — it writes its own cards into a separate `#market-cards` container. So the visible grid stayed "—" forever.
- Fix: `renderStaticMarketGrid(markets)` + `STATIC_GRID_MAP`, called from `refresh()`. It maps the 3 mismatched static keys to backend `getMarketState` keys: `dax→dax40`, `nikkei→nikkei225`, `shanghai→csi300` (other 17 match).
- `getMarketState` confidence is a 0–1 fraction (e.g. 0.381) → multiply by 100 for display.
**How to apply:** any future change to which markets/values show on the dashboard must update BOTH the static grid in `index.html` and `STATIC_GRID_MAP`/`renderStaticMarketGrid` — editing `renderMarkets` alone won't change what the user sees.

# Guardrail

User requires explicit approval before any change ("do not change the platform unless listed and approved"). User repeatedly pastes AI-generated "one-paste" snippets that assume a *simplified* app (e.g. `/api/live/{market}` index-only endpoint, `${key}-wps` element ids, `/rpc/...?market=` GET). These DO NOT match this app (RPC is POST `/api/{method}`; real ids are `wps-val-<key>`) and would break the real 2700-line dashboard / 1500-line server. Do not apply them — implement the correct fix for the real architecture instead.
