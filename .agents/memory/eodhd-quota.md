---
name: EODHD daily quota exhaustion (whole-dashboard freeze)
description: Why the WHOLE deployed dashboard goes dark mid-day — EODHD 100k/day API limit, not a crash.
---

# EODHD daily request quota — whole-app freeze

**Symptom:** Deployed dashboard "stops updating" / frozen for hours. ALL 25 markets (even
US) show 0 valid prices. Logs show cycles still firing every ~2 min and
`fetch_all_equity_batch: got 0/193 symbols (EODHD)` with `Batch fetch complete: 0 symbols`.
The VM is NOT stopped and there is NO crash/exception — fetches just return empty.

**Root cause (confirmed via direct API test):** EODHD returns **HTTP 402 "You exceeded your
daily API requests limit."** Account `dailyRateLimit` = **100,000/day**; it gets fully consumed.
Quota resets at **00:00 UTC** — app self-recovers at reset, then exhausts again later the same day.

**Why:** the live engine polls ~193 symbols every ~2 min, 24/7. EODHD real-time counts each
ticker as 1 request, so ~193 × ~696 cycles/day ≈ 130k+ calls/day > 100k limit. Closed markets
are re-fetched every cycle even though their price can't change — pure waste.

**How to apply / fixes (need user approval — touches fetch cadence):**
- Only fetch markets whose session is currently OPEN (skip closed) — biggest saving, most are
  closed most of the time.
- And/or lengthen the cycle interval (e.g. 2 min → 5–10 min).
- Or upgrade the EODHD plan (billing / user decision).
Diagnose with: `curl "https://eodhd.com/api/user?api_token=...&fmt=json"` → check apiRequests vs
dailyRateLimit; a single `/real-time/AAPL.US` call returning 402 = quota hit. Fetch code lives in
`backend/core/data_sources.py` (bulk real-time at ~line 195).
