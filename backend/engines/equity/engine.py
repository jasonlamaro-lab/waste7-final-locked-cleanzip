"""
Equity engine — weighted WPS, alignment, regime, signal, confidence.

All calculations are weight-aware. Every constituent contributes in proportion
to its index weight, not as a raw vote. This mirrors how the real index moves.

Multi-TF WPS formula:
  WPS = Σ_i [ weight_norm_i × (0.40×Δ5m + 0.30×Δ15m + 0.20×Δ30m + 0.10×Δ60m) ] × 100

This blends recency (5m leads) with trend confirmation (60m anchors).
Range: −100 (total sell pressure) → +100 (total buy pressure)
"""
from typing import Dict, List, Optional, Tuple

# Timeframe weights — loaded from active TRADE_STYLE at runtime so style changes take effect.
_TF_ORDER = ["5m", "15m", "30m", "60m"]


def _get_tf_weights() -> dict:
    try:
        from core.trade_style import get_tf_weights
        return get_tf_weights()
    except Exception:
        return {"5m": 0.40, "15m": 0.30, "30m": 0.20, "60m": 0.10}


# Module-level alias — kept for any callers that imported it directly.
# Reads the current style each time so it stays fresh.
def _TF_WEIGHTS_live() -> dict:
    return _get_tf_weights()


def _is_stale(sym_returns: dict) -> bool:
    """True if all timeframes report zero — likely a missing or stale price."""
    return all(sym_returns.get(tf, 0.0) == 0.0 for tf in _TF_ORDER)


def _normalise_weights(constituents: dict, returns: dict) -> Dict[str, float]:
    """
    Return weight_norm_i for constituents that have live, non-stale data.
    Stale constituents are excluded so they don't dilute the WPS signal.
    """
    total = sum(
        meta.get("weight", 0)
        for sym, meta in constituents.items()
        if sym in returns and not _is_stale(returns[sym])
    )
    if total <= 0:
        return {}
    return {
        sym: meta.get("weight", 0) / total
        for sym, meta in constituents.items()
        if sym in returns and not _is_stale(returns[sym])
    }


def calculate_wps(returns: dict, constituents: dict, market_slug: str = None) -> float:
    """
    Multi-Timeframe Weighted Price Strength.

    WPS = Σ_i [ weight_norm_i × blended_return_i ] × 100

    where blended_return_i = Σ_tf (tf_weight × Δ%_tf_i)

    Result: −100 to +100.
      0– 24  Dead / no pressure
     25– 39  Weak
     40– 59  Acceptable
     60– 74  Strong
     75–100  Sweetspot (best trades)
    """
    weights = _normalise_weights(constituents, returns)
    if not weights:
        return 0.0

    tf_weights = _get_tf_weights()
    wps = 0.0
    for sym, w_norm in weights.items():
        blended = sum(
            tf_weights[tf] * returns[sym].get(tf, 0.0)
            for tf in _TF_ORDER
        )
        wps += w_norm * blended

    return wps * 100.0


def _weighted_tf_score(returns: dict, constituents: dict, tf: str) -> float:
    """
    Weighted directional score for one timeframe.
    Returns a value in [−1, +1]: positive = weighted buy pressure.
    Stale constituents are excluded.
    """
    weights = _normalise_weights(constituents, returns)
    if not weights:
        return 0.0

    score = 0.0
    for sym, w_norm in weights.items():
        change = returns[sym].get(tf, 0.0)
        if change > 0:
            score += w_norm
        elif change < 0:
            score -= w_norm
    return score


def wps_momentum(returns: dict, constituents: dict) -> float:
    """
    WPS momentum — how much is pressure accelerating in the short term?

    Compares the 5m WPS component against the 60m WPS component.
    Positive = pressure building (5m stronger than 60m trend).
    Negative = pressure fading.

    Range: −100 to +100.
    """
    weights = _normalise_weights(constituents, returns)
    if not weights:
        return 0.0

    wps_5m  = sum(w * returns[sym].get("5m",  0.0) for sym, w in weights.items()) * 100
    wps_60m = sum(w * returns[sym].get("60m", 0.0) for sym, w in weights.items()) * 100
    return round(wps_5m - wps_60m, 2)


def calculate_alignment(returns: dict, constituents: dict = None,
                        live_mode: bool = False) -> Tuple[Optional[str], int]:
    """
    Measure how many timeframes show the same weighted direction.

    Uses weighted TF scores when constituents are provided.
    Returns (direction, alignment_count): direction = "BUY"|"SELL"|None, count = 0–4.
    """
    if constituents:
        scores = [_weighted_tf_score(returns, constituents, tf) for tf in _TF_ORDER]
        directions = [1 if s > 0 else (-1 if s < 0 else 0) for s in scores]
    else:
        def _raw(tf):
            up = sum(1 for v in returns.values() if v.get(tf, 0) > 0)
            dn = sum(1 for v in returns.values() if v.get(tf, 0) < 0)
            return 1 if up > dn else (-1 if dn > up else 0)
        directions = [_raw(tf) for tf in _TF_ORDER]

    buy  = directions.count(1)
    sell = directions.count(-1)
    alignment = max(buy, sell)

    if alignment >= 2:
        return ("BUY" if buy > sell else "SELL"), alignment
    return None, alignment


def classify_regime(wps: float, alignment: int, momentum: float = 0.0) -> str:
    """
    Regime classification.

    |WPS| < 5                          → CHOPPY_HIGH   (no trade)
    5 ≤ |WPS| < 10                     → CHOPPY_MEDIUM (no trade)
    |WPS| ≥ 10, alignment ≥ 3          → TRENDING
    |WPS| ≥ 10, momentum amplifies     → TRENDING_STRONG
    |WPS| ≥ 10, alignment 1–2          → REVERSAL
    """
    abs_wps = abs(wps)
    if abs_wps < 5:
        return "CHOPPY_HIGH"
    if abs_wps < 10:
        return "CHOPPY_MEDIUM"
    if alignment >= 3:
        # Momentum in the same direction as WPS = strong trend
        if momentum != 0 and (wps * momentum > 0) and abs(momentum) > 10:
            return "TRENDING_STRONG"
        return "TRENDING"
    return "REVERSAL"


def score_confidence(wps: float, alignment: int, momentum: float = 0.0) -> float:
    """
    Confidence score in [0, 1].

      60% — WPS magnitude (how strong is the weighted pressure?)
      30% — Alignment     (how many TFs agree?)
      10% — Momentum      (is pressure accelerating?)

    Sweet spot bonus: |WPS| 60-100 = confirmed pressure zone → +0.10 boost.
    This rewards the band where weighted pressure is unambiguously directional.
    """
    wps_abs = abs(wps)
    wps_score   = min(wps_abs, 100.0) / 100.0
    align_score = alignment / 4.0
    mom_score   = min(abs(momentum), 100.0) / 100.0 if momentum else 0.0

    confidence = (wps_score * 0.60) + (align_score * 0.30) + (mom_score * 0.10)

    # Sweet spot: strong confirmed pressure — give it a meaningful boost
    if 60.0 <= wps_abs <= 100.0:
        confidence += 0.10

    return round(min(max(confidence, 0.0), 1.0), 4)


def generate_signal(wps: float, direction: Optional[str], alignment: int,
                    momentum: float = 0.0, live_mode: bool = False) -> Optional[str]:
    """
    Emit BUY/SELL only when:
      - Not CHOPPY
      - |WPS| ≥ 10
      - alignment ≥ 2
      - direction is known
      - momentum not actively opposing the signal (fading pressure)
    """
    if direction is None:
        return None
    regime = classify_regime(wps, alignment, momentum)
    if regime.startswith("CHOPPY"):
        return None
    if abs(wps) < 10 or alignment < 2:
        return None
    # Block if momentum strongly opposes WPS (pressure fading fast)
    if momentum != 0 and (wps * momentum < 0) and abs(momentum) > 30:
        return None
    return direction
