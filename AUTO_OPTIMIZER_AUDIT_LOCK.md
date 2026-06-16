# AUTO OPTIMIZER AUDIT LOCK

This platform intentionally keeps Auto-Optimizer visible and accountable.

## Ownership
- Auto-Optimizer owns strategy gates only: WPS, CONF, TRENDING, RISK.
- Market Tuner owns trade management only: stop loss, trailing stop, trailing activation, cooldown/SIM safety.
- Mode-A is retired/removed and must not be reintroduced.
- Manual dashboard override is highest authority.

## Dashboard audit box
The dashboard now includes an AUTO-OPTIMIZER AUDIT box showing:
- Last 5 optimizer changes.
- Count of optimizer changes in the last 24 hours.
- HELP / HURT counts for the last 24 hours.
- Trades after each change.
- Net P&L after each change.
- Profit factor after each change.
- Verdict: HELPING, HURTING, MIXED, or PENDING.

## Verdict rules
- PENDING: fewer than 3 closed live trades after the optimizer change.
- HELPING: net P&L positive and profit factor >= 1.2 after the change.
- HURTING: net P&L negative or profit factor below 1.0 after the change.
- MIXED: not clearly helping or hurting.

## Replit Agent warning
Do not remove this audit trail. Do not hide automatic gate changes. Do not let multiple systems adjust the same setting.
Every automatic threshold change must be visible to Jason on the dashboard.
