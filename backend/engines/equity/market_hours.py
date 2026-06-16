"""
Exchange trading hours — defines when each market is open for business.

All times are in the exchange's LOCAL timezone. The is_open() function
converts UTC now to the local timezone for comparison.

Pre/post market is excluded — we only trade regular session hours.
Weekend checks are included (Mon=0 … Fri=4; Sat=5, Sun=6).
"""
from datetime import datetime, time
import pytz

# (open_time, close_time, timezone_name, trading_days)
# trading_days: tuple of weekday ints 0=Mon…4=Fri
_HOURS = {
    # ── Americas ──────────────────────────────────────────────────────────────
    "nasdaq100":  (time(9, 30),  time(16, 0),  "America/New_York",   (0,1,2,3,4)),
    "sp500":      (time(9, 30),  time(16, 0),  "America/New_York",   (0,1,2,3,4)),
    "dowjones":   (time(9, 30),  time(16, 0),  "America/New_York",   (0,1,2,3,4)),
    "tsx":        (time(9, 30),  time(16, 0),  "America/Toronto",    (0,1,2,3,4)),
    "bovespa":    (time(10, 0),  time(17, 30), "America/Sao_Paulo",  (0,1,2,3,4)),
    "merval":     (time(11, 0),  time(17, 0),  "America/Argentina/Buenos_Aires", (0,1,2,3,4)),

    # ── Europe ────────────────────────────────────────────────────────────────
    "ftse100":    (time(8, 0),   time(16, 30), "Europe/London",      (0,1,2,3,4)),
    "dax40":      (time(9, 0),   time(17, 30), "Europe/Berlin",      (0,1,2,3,4)),
    "cac40":      (time(9, 0),   time(17, 30), "Europe/Paris",       (0,1,2,3,4)),
    "eurostoxx50":(time(9, 0),   time(17, 30), "Europe/Paris",       (0,1,2,3,4)),
    "mib":        (time(9, 0),   time(17, 30), "Europe/Rome",        (0,1,2,3,4)),
    "ibex35":     (time(9, 0),   time(17, 30), "Europe/Madrid",      (0,1,2,3,4)),
    "aex":        (time(9, 0),   time(17, 30), "Europe/Amsterdam",   (0,1,2,3,4)),
    "omxs30":     (time(9, 0),   time(17, 25), "Europe/Stockholm",   (0,1,2,3,4)),
    "smi":        (time(9, 0),   time(17, 30), "Europe/Zurich",      (0,1,2,3,4)),

    # ── Asia-Pacific ──────────────────────────────────────────────────────────
    "asx200":     (time(10, 0),  time(16, 0),  "Australia/Sydney",   (0,1,2,3,4)),
    "nikkei225":  (time(9, 0),   time(15, 30), "Asia/Tokyo",         (0,1,2,3,4)),
    "hangseng":   (time(9, 30),  time(16, 0),  "Asia/Hong_Kong",     (0,1,2,3,4)),
    "csi300":     (time(9, 30),  time(15, 0),  "Asia/Shanghai",      (0,1,2,3,4)),
    "kospi":      (time(9, 0),   time(15, 30), "Asia/Seoul",         (0,1,2,3,4)),
    "twse":       (time(9, 0),   time(13, 30), "Asia/Taipei",        (0,1,2,3,4)),
    "sensex":     (time(9, 15),  time(15, 30), "Asia/Kolkata",       (0,1,2,3,4)),
    "set":        (time(10, 0),  time(16, 30), "Asia/Bangkok",       (0,1,2,3,4)),
    "nzx50":      (time(10, 0),  time(16, 45), "Pacific/Auckland",   (0,1,2,3,4)),

    # ── Middle East / Africa ──────────────────────────────────────────────────
    "tadawul":    (time(10, 0),  time(15, 0),  "Asia/Riyadh",        (0,1,2,3,6)),  # Sun–Thu
    "jse":        (time(9, 0),   time(17, 0),  "Africa/Johannesburg",(0,1,2,3,4)),
}

# Markets that don't have explicit hours default to this (fail-safe = closed)
_DEFAULT_CLOSED = False


def is_market_open(market: str, utc_now: datetime = None) -> bool:
    """Return True if the market is currently in its regular trading session."""
    if market not in _HOURS:
        return _DEFAULT_CLOSED   # unknown market = don't trade

    open_t, close_t, tz_name, trading_days = _HOURS[market]

    if utc_now is None:
        utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)
    elif utc_now.tzinfo is None:
        utc_now = utc_now.replace(tzinfo=pytz.utc)

    try:
        local_tz = pytz.timezone(tz_name)
    except Exception:
        return False

    local_now = utc_now.astimezone(local_tz)

    # Weekend check
    if local_now.weekday() not in trading_days:
        return False

    local_time = local_now.time().replace(second=0, microsecond=0)
    return open_t <= local_time <= close_t


def market_hours_str(market: str) -> str:
    """Human-readable session string for display."""
    if market not in _HOURS:
        return "Unknown"
    open_t, close_t, tz_name, _ = _HOURS[market]
    tz_short = tz_name.split("/")[-1].replace("_", " ")
    return f"{open_t.strftime('%H:%M')}–{close_t.strftime('%H:%M')} {tz_short}"


def get_all_hours() -> dict:
    """Return open/closed status for all markets."""
    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    return {
        market: {
            "open": is_market_open(market, now),
            "session": market_hours_str(market),
        }
        for market in _HOURS
    }
