# Waste 3 repair notes

## What was repaired

1. Centralised SQLite writes.
   - `backend/core/db.py` now has a process-wide `RLock` for all write connections.
   - `db_cursor()` and server write handlers now share the same writer path.
   - Read-only dashboard polling still uses fast read connections.

2. Closed the server bypass.
   - `backend/server.py` no longer opens its own raw SQLite writer connections.
   - `_get_ro_conn()` and `_get_rw_conn()` now route through `core.db`.

3. Added manual gate control endpoints.
   - `getGateSettings`
   - `setGateSetting`
   - `setMarketWpsThreshold`

4. Added simple dashboard controls.
   - Global WPS tightness.
   - Global CONF tightness.
   - Global TIME4 tightness.
   - Per-market WPS threshold input, for example `dax40` + `25`.

5. Fixed a risk reset display mismatch.
   - Reset values now line up with what gets saved.

## Deployment rule

Use this zip as the source of truth. Upload/import it into a clean Replit project or replace the current project files from this package, then run/test before republishing.

Do not mix this with older Replit checkpoints unless you want the same bug to come back wearing a fake moustache.
