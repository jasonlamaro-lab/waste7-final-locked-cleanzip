# READ FIRST - DO NOT REWRITE THE APP

This project has been repaired to preserve the existing Yahoo data path and trading engine. Do not replace the data feed, redesign the dashboard, change broker/data providers, or run a broad refactor.

Locked requirements:

1. Data source stays as-is for now: Yahoo/business data path for proving the platform for roughly one month.
2. Dashboard uses compact horizontal rows, not cards.
3. Show open markets only by default.
4. No grey text. Use hard white text, green for pass/positive, red for fail/blocking.
5. Remove the global HEALTH/TIME/TRENDING/WPS/RISK band from the visible UI.
6. Every market row must show: market, SIM/LIVE, TRADE YES/NO, signal, live price if available, WPS current/threshold with arrow, CONF current/threshold with arrow, ALN current/required, WR, PF, W/L, average win/loss.
7. Open trades and closed today use compact horizontal rows.
8. Keep global alignment control.
9. WPS and CONF threshold controls are per-market.
10. Do not discard current fixes, do not reset hard, do not pull/merge over the working state.

If Replit Agent is asked to deploy, it should only install, test, commit, push, and deploy this current version. No redesign. No new data provider. No “improvements” that change architecture.
