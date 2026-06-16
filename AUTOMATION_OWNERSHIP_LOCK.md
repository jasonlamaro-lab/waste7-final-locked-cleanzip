# AUTOMATION OWNERSHIP LOCK

This file is here so Replit Agent does not re-create overlapping agents and start another hidden tug-of-war.

## Final authority order

1. **Manual dashboard controls**
   - Highest authority.
   - If manual WPS or CONF is set for a market, automation must not override it.

2. **Auto-Optimizer**
   - Owns strategy thresholds only.
   - May tune WPS, CONF, TRENDING, RISK.
   - Must not change TIME4/alignment because Jason controls global alignment manually: 2 / 3 / 4.
   - Must log every change in `system_events` with source `auto_optimizer`.

3. **Market Tuner**
   - Owns trade management only.
   - May tune stop loss, trailing stop, trailing-stop activation, cooldown.
   - Must never change WPS.
   - Must never change CONF.
   - Must never change TIME4/alignment.
   - Must log every change in `system_events` with source `market_tuner`.

4. **Mode-A**
   - Retired and removed.
   - Do not re-enable.
   - Do not rebuild.
   - It duplicated WPS control and clashed with Auto-Optimizer.

## Stop / trailing logic

Jason's current preferred stop loss is tight, around **0.8%**, because the platform is meant to pick direction. If the market moves against the trade immediately, the trade is probably wrong and should be cut quickly.

Market Tuner must protect that idea:

- Cut bad trades quickly.
- Do not keep tightening the trailing stop until it chops normal profits.
- If trailing-stop wins are too small compared with losses, loosen trailing stop slightly.
- Trail should arm only once there is enough profit to protect.

## Why this matters

Only one system can own each control surface. The old version had Auto-Optimizer, Mode-A, and Market Tuner all touching WPS. That made it impossible to know who changed what or whether the change helped.
