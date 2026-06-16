# Multi-Engine Trading Management System — PRD

## Original Problem Statement
Build a management system for autonomous trading bots across Equity, Crypto Scalp, and Crypto Long engines with LIVE execution on Pepperstone via cTrader Open API. User demands: absolute control over live-trading permissions, horizontal layouts, high-contrast UI, and a strictly tracked "Kitty".

## Architecture
- Static HTML dashboard (`/app/frontend/public/public/dashboard-v61.js`) + FastAPI backend + SQLite
- 3 Trading Engines: Equity (25 markets), Crypto Scalp (20 coins), Crypto Long (10 coins)
- 60s trading cycle, 30s trade updates
- Broker: **cTrader Open API over Protobuf TCP** (not REST — Spotware has no REST for orders)
- Twisted reactor thread running `ctrader_balance_mirror.py` holds persistent TCP auth

## Core Rules (SACRED)
1. Real Kitty — never reset on boot, no SIM settlement affects balance
2. All dollar amounts: 2 decimal places
3. No confirmation on cash out — instant close
4. Dashboard shows LIVE trades ONLY (SIM runs silently in background for swarm learning)
5. Flags on equity, token symbols on crypto
6. Per-engine circuit breaker: LIVE P&L < -$0.50 → SIM
7. CHOPPY regime banned for all engines except `crypto_long`
8. Global LIVE_MODE removed — per-market LIVE flag is authoritative

## Auto-Live Gating (SIM → LIVE)
- PF ≥ 1.5, WR ≥ 60%, Expectancy ≥ $0.05, min 10 SIM trades
- Demotion: WR < 45% → DEGRADED, WR < 35% → brain wash

## Key Files
- `/app/backend/services/execution/ctrader_balance_mirror.py` — TCP broker client (Twisted/Protobuf)
- `/app/backend/services/execution/pepperstone_broker.py` — live order wrapper
- `/app/backend/services/execution/trade_executor.py` — LIVE/SIM router
- `/app/backend/services/execution/trade_manager.py` — exit manager (now closes LIVE positions too)
- `/app/backend/services/lifecycle/market_tuner.py` — per-market autonomous threshold tuning
- `/app/backend/core/db.py` — SQLite schema (+ new broker_* columns on `trades`)

## What's Implemented

### [Feb 2026] Mode-A threshold governor + kitty rewrite (THIS SESSION)
- **Async engine runner** (`/app/backend/core/engine_runner.py`): replaces threaded `_background_loop` with asyncio task in FastAPI lifespan. Per-cycle telemetry persisted to new SQLite tables (`engine_state`, `cycle_telemetry`). Blocking I/O wrapped in `asyncio.to_thread()` so the event loop never stalls. Crash-isolated with error backoff. Single instance via `uvicorn --workers 1` — no Mongo lock needed.
- New endpoints: `getEngineState`, `getCycleTelemetry` (JSON-RPC over `/api/`).
- **Mode-A side-loop**: autonomous per-market WPS threshold governor (`/app/backend/services/mode_a/`):
  - Verbatim drop-in `mode_a_agent.py` (state machine: IDLE → COLLECTING → EVALUATING → ADJUSTING → COOLDOWN)
  - Spec v1: trigger=50 settled trades/market, floor=40 (sacred), ceiling=85, cooldown=20, sample=100, Rule A only (RAISE on false-signal losers)
  - `runner.py` adapter: DB-backed thresholds load/persist, fetch_last_trades from `trades` table (parses WPS from `reason` field), audit trail in `mode_a_threshold_history`
  - Hooked into `kitty_manager.settle_trade` — runs on every settled trade, never touches execution
  - Initial bug in module's `last_eval_trade_count` update logic flagged and patched (now gated on EVAL→COOLDOWN transition only)
  - Endpoint: `POST /api/getModeAStatus`, `POST /api/getModeAHistory`
  - Integration test: `/app/backend/tests/test_mode_a.py` — RAISE fires correctly when synthetic 60 losing trades feed in
- **Mode-A Live Ticker** (frontend): fixed bottom strip showing `[market · threshold | STATE | s<since> | cd<cooldown>]` chips for all 25 markets, polled every 5s via `getModeAStatus`. Color-coded states (IDLE grey · COLLECTING blue · EVALUATING yellow · ADJUSTING orange · COOLDOWN purple). Horizontally scrollable.
- **Kitty philosophy rewrite** (single-pool, no reserve):
  - OPEN → `balance -= stake`; CLOSE → `balance += stake + pnl`; balance ≤ 0 → auto-reset to $10,000
  - "Reserved" concept fully removed from `kitty_manager.py`, `server.py`, frontend
  - Settles on every close (SIM + LIVE) — was previously LIVE-only
  - One-shot DB rebase aligned balance to philosophy
  - Frontend faceplate reads `kitty.balance` directly (no client-side math)
- **WPS gate unified → |WPS| ≥ 40 AND alignment ≥ 3** for both SIM and LIVE; regime: `<20` CHOPPY_HIGH, `<40` CHOPPY_MEDIUM, `≥40` TRENDING/REVERSAL
- **Frontend**: stale "Last cycle X ago" purged; only dynamic `Next cycle in XX s` countdown remains
- **IG broker**: confirmed dormant

### [Apr 19 2026] Prior session
- 3-engine platform, dashboard, market drill-downs, trade cards
- Per-market self-tuning (`market_tuner.py`), dynamic equity constituents via yfinance
- Kitty audit fix (SIM no longer touches balance)
- CoinGecko + Coinbase fallback
- Notifier scaffold (Twilio + Resend, awaiting keys)
- First cTrader TCP Protobuf order fired (BTC) — but execution flow incomplete

### [Apr 20 2026] THIS SESSION — LIVE trading pipeline hardened end-to-end
- **ProtoOAOrderErrorEvent (pt=2132)** handler added — broker rejections no longer dropped silently
- Fixed `ProtoOATraderUpdatedEvent` payload type (was `2125` → correct is `2123`)
- Added catch-all logging for any unknown payload type (first-occurrence only)
- **New `trades` columns**: `broker_order_id`, `broker_position_id`, `broker_fill_price`, `broker_status`, `broker_error`
- LIVE trades now inserted as `status='PENDING'` first; broker ExecutionEvent flips to `OPEN` (via label `tid-<id>`) or `REJECTED`
- Per-symbol cooldowns on broker errors (NOT_ENOUGH_MONEY=1h, MARKET_CLOSED=5m, BAD_VOLUME=1h, etc.)
- `ProtoOASymbolByIdReq (2116)` fetched for all traded symbols → cached `minVolume`, `stepVolume`, `digits`, `lotSize`
- `place_order` auto-scales volume up to `minVolume` and snaps to `stepVolume`
- SL rounded to symbol's allowed `digits`
- Absolute SL no longer sent on MARKET orders (was causing INVALID_REQUEST); stashed and applied post-fill via `ProtoOAAmendPositionSLTPReq (2110)` once position arrives
- Full execution event handler: FILLED → DB update with fill price + SL amend; REPLACED → update actual fill price; REJECTED/CANCELLED → mark row REJECTED and release Kitty
- REJECTED LIVE trades filtered out of UI (they were cluttering)
- `ProtoOAClosePositionReq (2111)` wired into `trade_manager`: when SL/TS/TP/TIME_EXIT fires on a LIVE trade with a `broker_position_id`, the real Pepperstone position is closed over TCP before the local row flips to CLOSED
- Broker position volumes cached from reconcile (pt=2125) so close requests carry correct volume
- **UI fix**: `getMarketState` now includes `broker_mirror` snapshot → KITTY panel shows green "● BROKER LIVE" badge and `PEPPERSTONE` label when authorised
- New debug/admin endpoints:
  - `GET  /api/ctrader/test-order?symbol=X&side=BUY&volume=1`
  - `GET  /api/ctrader/events?limit=50` — broker event ring buffer + cooldowns + cached symbol details
  - `POST /api/ctrader/clear-cooldown?symbol=X`
  - `POST /api/ctrader/close-position?position_id=N&volume=0`

### [Apr 20 2026] Part 2 — Pre-flight margin, AUD decode, Unrealized P&L
- **Pre-flight margin check**: `ProtoOAExpectedMarginReq (2139)` fired before each order (caller-side, not reactor — avoids deadlock). Response cached per-symbol for 5 min, scales linearly. Orders that would exceed `free_margin × 0.9` are rejected locally with a `PREFLIGHT_REJECT` event and 5-min cooldown, never hitting the broker.
- **AUD currency decode**: `ProtoOAAssetListReq (2112)` on auth caches 2956 assets (`1 → AUD`, `2 → CAD`, etc). Trader state now shows `currency: "AUD"` (was `"1"`).
- **Unrealized P&L**: Broker reconcile now captures `position.price` (entry) + swap + commission per position; `_compute_unrealized_pnl` sums `(spot - entry) × contract × side_sign` using `core.data_sources._crypto_cache`. Equity and free_margin updated to include it. UI kitty panel gets new `OPEN POS / UNREALISED P&L / USED MARGIN` column. If spot prices are missing for a cycle, last known value is kept (no flapping to 0).
- Bug fix: `_update_state_from_trader` no longer zeroes `used_margin` / `free_margin` (those are owned by the reconcile handler; trader-update events don't carry margin data).

## Pending / Next

### P1 — Polish
- Fetch `ProtoOAExpectedMarginReq (2139)` before order to pre-compute required margin and skip unaffordable orders proactively (instead of relying on post-reject cooldown)
- Decode `depositAssetId` → "AUD" (currently shown as raw id "1")
- Unrealized P&L from broker on open positions (shown in Kitty panel)
- Reconcile external manual closures (if user closes in cTrader Desktop, catch ExecutionEvent and close DB row)

### P2 — Awaiting credentials
- Twilio: Account SID + Auth Token + From Number → https://console.twilio.com
- Resend: API key → https://resend.com/api-keys
- Once Jason provides, notifier.py is ready (dedupe + multi-channel)

### P3 — Refactor
- Split `ctrader_balance_mirror.py` (950 lines) into `mirror/client.py`, `mirror/handlers.py`, `mirror/state.py`
- Pytest harness for the TCP handlers (mock protobuf responses)
