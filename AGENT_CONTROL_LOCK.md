# Agent / Manual Control Lock

This build keeps Yahoo/data wiring untouched and changes agent governance only.

## Current WPS operating range
- Default WPS threshold: 10
- Automation floor: 5
- Automation ceiling: 30
- Old 40–85 Mode-A/tuner limits were removed because live market WPS readings are commonly around 15–19 and 40 blocks normal operation.

## Manual priority rule
Dashboard manual settings win. If a market has a manual WPS or CONF override, automation must not change that setting.

Manual flags stored in `market_state.config`:
- `manual_wps_override`: dashboard-set WPS threshold, agent/optimizer/tuner must not change WPS.
- `manual_conf_override`: dashboard-set CONF gate, optimizer must not change CONF.
- `manual_gate_TIME4`: per-market TIME4 override if ever used. Global alignment remains user-controlled.

## What the auto systems still do
- `auto_optimizer.py`: reviews recent trades and may tune unmanaged markets only. It no longer moves TIME4/alignment.
- `mode_a_agent.py`: WPS governor only, now 5–30 not 40–85, and skipped for manual WPS markets.
- `market_tuner.py`: reacts after losing streaks. It no longer forces WPS back to 40 and does not change WPS when manual WPS is active.

## Required UI behaviour
Show the last agent/optimizer/tuner action from `system_events`, so Jason can see whether automation is improving or hurting each market. No invisible ghost-admin changes.
