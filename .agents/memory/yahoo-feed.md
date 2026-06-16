---
name: Yahoo Finance price feed (migrated off EODHD)
description: The live equity price feed now uses Yahoo Finance (yfinance), not EODHD — why and the key gotchas.
---

# Yahoo Finance feed

The equity price feed was migrated from EODHD to **Yahoo Finance (yfinance)** because EODHD's
100k/day request quota was exhausted mid-day every day (see eodhd-quota.md). User approved the
provider switch explicitly; platform/approach otherwise unchanged.

**Key facts:**
- Client: `backend/services/data/yahoo_client.py` — same public surface the old EODHD client had
  (`get_price`, `get_prices_bulk`, `get_intraday_ohlc`, `get_intraday_ohlc_batch`,
  `get_intraday_5m_return`). Multi-timeframe returns are PERCENTAGES (×100) to match the old contract.
- Universe tickers are ALREADY yfinance-format (.AX/.T/.NS/etc.) — no symbol mapping needed. EODHD's
  `_SUFFIX_MAP`/`INDEX_TICKERS` are now unused.
- The per-cycle feed uses ONE batched `yf.download(..., group_by="ticker")`, not per-symbol calls.
  Single-ticker downloads have flat columns; multi-ticker have a (ticker, field) MultiIndex — handle both.
- Yahoo is free with **no hard daily cap**, but it can SOFT-throttle (429 / empty rows) under heavy
  polling. It self-heals; it does NOT go dark for the rest of the day like EODHD did.
- Coverage is broader than EODHD: all 25 markets now return data (was 18). **Consequence:** the
  dashboard's hardcoded `UNCOVERED_MARKETS` (7 "NOT CONNECTED" badges) is now stale — those markets
  are live on Yahoo. Flip them to LIVE when the user wants.

**Install gotcha:** the package tools (uv) and plain `pip` both fail here (they target the read-only
Nix store / externally-managed env). Install Python packages with
`python3 -m pip install --break-system-packages --target=/home/runner/workspace/.pythonlibs/lib/python3.11/site-packages <pkg>`.

**Cadence:** `SYSTEM_CYCLE_SECONDS` default lowered 120→60; `_INTRADAY_TTL` in yahoo_client lowered
300→55 so each cycle actually refetches. Keep TTL just under the cycle interval.
