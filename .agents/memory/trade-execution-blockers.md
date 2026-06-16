---
name: Trading engine — why trades stop firing
description: The real signal/gate chain that must all pass for a trade to open; non-obvious blockers found during a "no trades firing" incident.
---
# Trade execution chain (equity engine)

A trade only opens if ALL of these pass, in order. Several are NOT the obvious "gate":

1. **Engine must emit a direction** — `generate_signal` in `engines/equity/engine.py` returns
   BUY/SELL only when `|WPS| >= threshold`, `alignment >= 2`, and regime not CHOPPY
   (`classify_regime` bands). This internal WPS threshold is the FIRST and primary wall — if
   it's too high relative to live WPS, signal is `None` and no downstream gate ever runs.
   **The gates.py `WpsGate.base_threshold` is a SEPARATE, downstream filter** — lowering it does
   nothing if the engine never produced a signal. "Drop the WPS" usually means the engine threshold.

2. **TIME4 gate** reads `ctx.timeframes` as a `{"5m":1/-1/0,...}` dict. The caller (`core/system.py`
   `run_equity_cycle`) builds this dict from `result["timeframes"]` where each entry's `dir` is
   **"BUY"/"SELL"/"NEUTRAL"** (set in `market_engine.py`). A string mismatch here (e.g. checking
   "UP"/"DOWN") silently maps every TF to 0 → TIME4 always "0/4 < required 2" → EVERY trade blocked,
   regardless of signal strength. Watch this whenever no trades fire but signals look directional.

3. Other pipeline blockers (`core/pipeline.py maybe_execute_trade`): paused, max concurrent,
   one-open-position-per-market, loss cooldown, market-hours (`is_market_open`), gates
   (HLTH/TIME4/TRENDING/WPS/CONF/RISK), lifecycle DEGRADED/RESET, swarm pattern gate, auto-optimizer
   5-loss suppression, kitty stake reservation.

# auto_optimizer doom loop
`services/intelligence/auto_optimizer.py` cranks a market's gates to "sweet spot" (WPS≥60 via
per-market `market_state.config`) after 3 consecutive CLOSED losses (reads `trades` table). Clearing
the `trades` table + nulling `market_state.config` neutralizes it; it re-applies only after 3 new losses.

# Diagnosing
Check `signals` table: if `signal` is mostly NULL → it's the engine threshold (#1). If signals are
directional but `trades` stays 0 → it's a pipeline gate; the workflow log prints
"Trade blocked by <GATE> gate: <reason>" for the exact cause.
