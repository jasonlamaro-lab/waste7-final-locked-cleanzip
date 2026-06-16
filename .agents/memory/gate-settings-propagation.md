---
name: Gate settings propagation (UI → DB → engine → card)
description: How per-market gate controls reach the trade engine and the market card; the WPS abs_threshold contract and the duplicated-formula drift risk.
---

# Gate settings propagation

Per-market gate overrides live in `market_state.config` (JSON). The trade path passes
the market **key** (e.g. `jse`, `omxs30`) as the market id, which matches the config
key, so `load_settings(market)` resolves per-market overlays correctly.
`load_settings` overlays `config["gates"][<GATE>]` (tightness/range) onto global gate
defaults.

## Manual controls (GATE CONTROL panel) — all per-market
- **Alignment** → saved as per-market `config.gates.TIME4.tightness` (UI sends
  `setGateSetting` WITH `market`). Time4 gate: `required = round(2 + tightness*range*2)`.
- **CONF** → saved per-market `config.gates.CONF.tightness`. ConfGate:
  `effective = 0.20 + tightness*range` (global CONF range = 0.35).
- **WPS** → saved as TOP-LEVEL `config.wps_threshold` (absolute 0–100), NOT under
  `config.gates`. `load_settings` copies it into `gates.WPS.abs_threshold`; WpsGate
  prefers `abs_threshold` when present, else falls back to `base(10) + tightness*range*100`.

**Why WPS is special:** it is an absolute threshold, not a tightness. Tightness alone
can't represent thresholds below the base (~10), so the absolute path is required.

## Market card display
`_marketThresholds()` in dashboard-v61.js reads the SAME per-market `config` (via
`lifecycle[key].config`, a raw JSON string it parses) for WPS, CONF and ALN, each
falling back to global tightness when no per-market override exists. So adjusting a
manual control updates both the engine gate and the card figure for that market.

## Drift risk (known, non-blocking)
The card recomputes thresholds with formulas/params HARDCODED in JS (CONF 0.35,
TIME4 range 1, WPS default 10). These duplicate the Python gate math. If a gate's
`range` or a global tightness ever changes away from defaults, the card can drift
from engine truth for NON-manual markets. Fix if it matters: derive card thresholds
from a single shared source instead of re-deriving in JS.

**How to apply:** any change to gate threshold math must be mirrored in BOTH
`backend/core/gates.py` and `_marketThresholds()` until the formulas are unified.
