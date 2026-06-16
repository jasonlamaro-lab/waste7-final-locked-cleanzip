"""
Trade Style — configures how aggressively the platform enters and exits.

SCALP  — 5–30 min holds. Tight SL/TS. 5m signal dominant. High frequency.
SWING  — 1–4 hour holds. Moderate SL/TS. Balanced TF blend. Default.
HOLD   — 4–24 hour holds. Wide SL/TS. 60m signal dominant. Low frequency.

Set TRADE_STYLE=SCALP|SWING|HOLD in .env (default: SWING).

All SL/TS values are % of the entry price on the underlying asset.
The platform checks current_price vs entry_price every TRADE_UPDATE_INTERVAL seconds.
"""
import os

# ── Style definitions ─────────────────────────────────────────────────────────

STYLES = {
    "SCALP": {
        "description":          "5–30 min holds — tight stops, high frequency",
        "sl_pct":               0.50,   # stop loss 0.5% of price
        "ts_pct":               0.35,   # trailing stop 0.35%
        "ts_activation_pct":    0.25,   # TS arms once up 0.25%
        "wps_min":              50.0,   # need strong pressure to scalp
        "alignment_min":        3,      # 3/4 TFs must agree
        "tf_weights": {                 # 5m almost everything
            "5m": 0.60, "15m": 0.25, "30m": 0.10, "60m": 0.05,
        },
        "cycle_seconds":        60,     # check signals every 60s
        "update_interval":      20,     # check open trades every 20s
        "wps_gate_tightness":   0.30,   # tighter WPS gate (need clearer signal)
        "expected_hold_mins":   "5–30",
    },
    "SWING": {
        "description":          "1–4 hour holds — balanced, default mode",
        "sl_pct":               1.50,   # stop loss 1.5%
        "ts_pct":               1.00,   # trailing stop 1.0%
        "ts_activation_pct":    0.80,   # TS arms once up 0.8%
        "wps_min":              35.0,
        "alignment_min":        2,
        "tf_weights": {                 # balanced, 5m still leads
            "5m": 0.40, "15m": 0.30, "30m": 0.20, "60m": 0.10,
        },
        "cycle_seconds":        120,
        "update_interval":      60,
        "wps_gate_tightness":   0.15,
        "expected_hold_mins":   "60–240",
    },
    "HOLD": {
        "description":          "4–24 hour holds — wide stops, trend following",
        "sl_pct":               3.00,   # stop loss 3%
        "ts_pct":               2.00,   # trailing stop 2%
        "ts_activation_pct":    1.50,   # TS arms once up 1.5%
        "wps_min":              25.0,   # accept weaker signals — longer trend
        "alignment_min":        2,
        "tf_weights": {                 # 60m anchors the signal
            "5m": 0.20, "15m": 0.25, "30m": 0.30, "60m": 0.25,
        },
        "cycle_seconds":        300,    # check every 5 mins
        "update_interval":      120,    # check open trades every 2 mins
        "wps_gate_tightness":   0.00,   # most permissive
        "expected_hold_mins":   "240–1440",
    },
}

DEFAULT_STYLE = "SWING"


def get_style() -> dict:
    """Return the active style config, read from TRADE_STYLE env var."""
    name = os.getenv("TRADE_STYLE", DEFAULT_STYLE).upper()
    return {"name": name, **STYLES.get(name, STYLES[DEFAULT_STYLE])}


def get_tf_weights() -> dict:
    """Return TF weight dict for the active style."""
    return get_style()["tf_weights"]


def get_sl_ts() -> tuple[float, float, float]:
    """Return (sl_pct, ts_pct, ts_activation_pct) for the active style."""
    s = get_style()
    return s["sl_pct"], s["ts_pct"], s["ts_activation_pct"]


def all_styles() -> dict:
    """Return all style definitions for display."""
    active = os.getenv("TRADE_STYLE", DEFAULT_STYLE).upper()
    return {
        name: {"active": name == active, **cfg}
        for name, cfg in STYLES.items()
    }
