---
name: EODHD market coverage (7 stale markets)
description: Why 7 of 25 markets are permanently stale — provider coverage, not a code bug.
---

# EODHD coverage — the 7 stale markets

The dashboard's "partial data feed" with **7 stale markets** is an EODHD plan/coverage
limitation, NOT a bug. The 18 covered markets are fully live.

**Stale 7 (native exchanges not covered):** nzx50 (NZ `.NZ`), mib (Milan `.MI`),
nikkei225 (Tokyo `.T`), sensex (India `.NS`), set (Thailand `.BK`), tadawul (Saudi `.SR`),
jse (South Africa `.JO`).

**Evidence (direct EODHD API tests):**
- `intraday` endpoint (the app's live feed via `get_intraday_ohlc`) returns **404 Ticker
  Not Found** for all of these exchanges (`.NS`, `.T`, `.MI` confirmed). US (`AAPL.US`) works.
- `real-time` endpoint is mixed: 404 for `.MI`/`.NZ`/`.SR`; `"NA"` values for `.NS`/`.T`/`.JO`;
  only Thailand `DELTA.BK` returned real data.
- EODHD `search` for UniCredit → only LSE/US-ADR/XETRA (no Milan); SoftBank → only US/Frankfurt
  (no Tokyo). Confirms the native exchanges aren't in this subscription; only US/UK/DE listings.

**Connection indicator (built):** Dashboard shows a per-market LIVE vs NOT CONNECTED /
NO FEED badge. It is **coverage-based, not freshness-based** — driven by a hardcoded set of
the 7 uncovered keys, NOT by `is_live`/`stale`. **Why:** a covered market that is merely
*closed* must still read LIVE (and go live when its session opens); freshness would wrongly
flag it. The 7-key set is duplicated in `dashboard-v61.js` (`UNCOVERED_MARKETS`) and
`index.html` (`pollDataQuality` `UNCOVERED`) — keep them in sync if coverage ever changes.

**Conclusion / how to apply:** Cannot be fixed in code — the data isn't in the plan.
Real options: (a) leave as-is (18 live), (b) relabel/hide the 7 in the UI, (c) Thailand
*alone* is partially recoverable via a real-time fallback, (d) upgrade EODHD plan or switch
provider to cover those exchanges (user decision — billing/approach). Do NOT re-investigate
ticker formats; the symbols are correct, the exchanges just aren't covered.
