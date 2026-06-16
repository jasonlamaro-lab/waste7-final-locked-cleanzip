---
name: Dashboard market price source
description: Where the per-market live price on the dashboard tiles comes from, and why it's an anchor stock not the index level
---

# Market tile price = engine STATE anchor price, not the signals table

The `getMarketState` RPC builds its `markets` dict from the `signals` DB table, which has NO price column. The live per-market price lives only in the in-memory engine `STATE["markets"][<market>]["price"]`, set each cycle in `core/system.py::run_equity_cycle` from the market's **canonical anchor constituent** (e.g. ftse100→HSBA.L, dax40→SAP.DE, cac40→MC.PA), not the index level.

**Rule:** if a dashboard field needs a value that the engine computes per-cycle (price, timeframes, direction, etc.), the `getMarketState` handler must explicitly copy it from `_mem = STATE["markets"]` into the response `entry`. It only copies a whitelist — adding a new live field means adding a copy line there too.

**Why:** prices were blank for all open markets except the one with an open trade (which got `trade.current_price` on the frontend). Root cause was the handler copying only `timeframes`/`direction` from STATE and dropping `price`.

**Consequence to remember:** the tile price is an anchor *stock* price (~1407 for FTSE), NOT the index level (~8000). If the user wants the real index quote, a separate index-quote feed is needed — the current number is intentionally the anchor the engine trades/values on.

**Frontend:** `dashboard-v61.js::_marketPrice`/`renderMarkets` read `m.price ?? m.current_price ?? m.last_price`, fallback `trade.current_price`. `_priceArrow(key, priceRaw)` tracks last price per market in `_lastPriceTrend` → ↑green/↓red/→flat; first render is always flat.
