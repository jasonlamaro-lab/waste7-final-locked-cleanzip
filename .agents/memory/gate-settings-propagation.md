---
name: Gate settings propagation (UI → DB → engine)
description: Which gate controls actually reach the trade engine, and the WPS storage-location trap.
---

# Gate settings propagation

Per-market gate overrides live in `market_state.config` (JSON). The engine's
settings loader overlays ONLY the `config["gates"][<GATE>]` sub-object (tightness/range)
on top of the global gate defaults. The trade path passes the market **key**
(e.g. `omxs30`, `dax40`) as the market id, which matches the per-market config key,
so per-market overlays do resolve correctly.

What propagates to gate evaluation:
- **Alignment** ✅ — saved as the GLOBAL TIME4 tightness; Time4 gate derives
  required-gates (2/3/4) from `round(2 + tightness*range*2)`.
- **CONF** ✅ — saved per-market into `config["gates"]["CONF"].tightness`; overlaid
  by the loader; CONF gate reads it.
- **WPS** ❌ — saved per-market into TOP-LEVEL `config["wps_threshold"]`, NOT into
  `config["gates"]["WPS"]`. The loader never copies it, and the WPS gate computes
  its threshold purely from base+tightness. So a saved WPS threshold is ignored by
  trade evaluation even though tile UI displays it (tile reads `wps_threshold` directly).

**Why:** two different storage locations for the same concept (top-level absolute
value vs. per-gate tightness override) — a silent UI-vs-engine mismatch.

**How to apply:** to make WPS honor the saved value, inject `config["wps_threshold"]`
into the loaded `gates["WPS"]` (e.g. as an `abs_threshold`) and have the WPS gate
prefer it over base+tightness. This allows the full 0–100 range (tightness alone
can't represent thresholds below the base ~10).
