"""
MarketEngine — per-market engine that runs the full weighted WPS pipeline.
"""
from engines.equity.engine import (
    calculate_wps, calculate_alignment, classify_regime,
    generate_signal, score_confidence, wps_momentum, _weighted_tf_score,
)
from engines.equity.markets import MARKET_DEFINITIONS
from core.config import LIVE_MODE


class MarketEngine:
    def __init__(self, slug: str):
        from engines.equity.constituent_refresh import get_constituents
        dyn = get_constituents(slug) or {}
        self.market_name = slug
        if dyn.get("constituents"):
            self.constituents = dyn["constituents"]
            self.constituents_source = "refreshed" if dyn.get("refreshed_at") else "static"
            self.constituents_refreshed_at = dyn.get("refreshed_at")
        else:
            defn = MARKET_DEFINITIONS.get(slug)
            if not defn:
                raise ValueError(f"No market definition for '{slug}'")
            self.constituents = defn["constituents"]
            self.constituents_source = "static"
            self.constituents_refreshed_at = None
        self.weights = {sym: meta["weight"] for sym, meta in self.constituents.items()}

    def run(self, market_prices: dict) -> dict:
        """
        Run the weighted WPS pipeline for this market.
        market_prices: {symbol: {"price": float, "5m": pct, "15m": pct, "30m": pct, "60m": pct}}
        """
        returns = {}
        for sym in self.constituents:
            if sym in market_prices:
                p = market_prices[sym]
                returns[sym] = {
                    "5m":  p.get("5m",  0.0),
                    "15m": p.get("15m", 0.0),
                    "30m": p.get("30m", 0.0),
                    "60m": p.get("60m", 0.0),
                }

        if not returns:
            return {"signal": None, "wps": 0.0, "alignment": 0, "regime": "UNKNOWN",
                    "confidence": 0.0, "momentum": 0.0, "timeframes": []}

        wps      = calculate_wps(returns, self.constituents)
        momentum = wps_momentum(returns, self.constituents)

        direction, alignment = calculate_alignment(
            returns, constituents=self.constituents, live_mode=LIVE_MODE
        )

        regime     = classify_regime(wps, alignment, momentum)
        signal     = generate_signal(wps, direction, alignment, momentum, live_mode=LIVE_MODE)
        confidence = score_confidence(wps, alignment, momentum)

        # Per-timeframe breakdown
        timeframes = []
        for tf in ("5m", "15m", "30m", "60m"):
            tf_score = _weighted_tf_score(returns, self.constituents, tf)
            tf_dir   = 1 if tf_score > 0 else (-1 if tf_score < 0 else 0)

            total_w, total_r = 0.0, 0.0
            for sym, meta in self.constituents.items():
                if sym in returns:
                    w = meta.get("weight", 0)
                    total_w += w
                    total_r += w * returns[sym].get(tf, 0.0)
            avg_pct = (total_r / total_w) if total_w > 0 else 0.0

            timeframes.append({
                "tf":      tf,
                "dir":     "BUY" if tf_dir > 0 else ("SELL" if tf_dir < 0 else "NEUTRAL"),
                "score":   round(tf_score, 4),
                "avg_pct": round(avg_pct * 100, 3),
            })

        return {
            "signal":     signal,
            "wps":        round(wps, 2),
            "momentum":   round(momentum, 2),
            "alignment":  alignment,
            "regime":     regime,
            "confidence": confidence,
            "direction":  direction,
            "timeframes": timeframes,
        }
