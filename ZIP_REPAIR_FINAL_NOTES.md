# Waste 3 Locked Clean Repair Notes

This package is the fixed source-of-truth ZIP for fresh GitHub/Replit upload.

## Final repair pass
- Fixed fresh Replit Python dependency install by populating `pyproject.toml` dependencies.
- Restored missing backend RPC handlers:
  - `getEngineState`
  - `getCycleTelemetry`
  - `getGateSettings`
  - `setGateSetting`
  - `setMarketWpsThreshold`
- Confirmed there are no missing `_handle_*` functions referenced by the RPC registry.
- Confirmed frontend JavaScript syntax passes `node --check`.
- Confirmed backend `server.py` imports successfully.
- Confirmed the five repaired RPC handlers execute against a fresh SQLite DB.

## Locked rules still preserved
- Yahoo data path not replaced.
- Dashboard horizontal-row UI retained.
- SQLite write-lock repair retained.
- Mode-A remains retired.
- Auto-Optimizer remains owner of WPS/CONF/TRENDING/RISK.
- Market Tuner remains limited to stop loss, trailing stop, trailing activation, cooldown.
- Manual per-market overrides set manual flags so automation does not silently overwrite them.

## Upload rule
Upload this as a new clean project/repo. Do not let Replit Agent refactor it. Only install dependencies and start the app.
