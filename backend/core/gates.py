"""
Trading gate system — 6 sequential gates that must all PASS before a trade fires.

Each gate has a single slider (tightness 0.0–1.0) that shifts its threshold up
within a fixed range. Settings are loaded from gates_settings.json (auto-created
with defaults on first run).

Gate order: HLTH → TIME4 → TRENDING → WPS → CONF → RISK
"""
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "gates_settings.json")
_SETTINGS_FILE = os.path.normpath(_SETTINGS_FILE)

_DEFAULT_SETTINGS: Dict[str, Any] = {
    "gates": {
        "HLTH":     {"tightness": 0.00, "range": 0.00},  # binary — always strict
        "TIME4":    {"tightness": 0.00, "range": 1.00},  # 3/4 TFs required (loosest)
        "TRENDING": {"tightness": 0.00, "range": 0.30},  # alignment ≥ 2 (loosest)
        "WPS":      {"tightness": 0.00, "range": 0.80},  # |WPS| ≥ 20..100 (tightness=0.50 → effective=60)
        "CONF":     {"tightness": 0.00, "range": 0.35},  # confidence ≥ 0.40 (loosest)
        "RISK":     {"tightness": 0.00, "range": 0.40},  # daily loss cap at 10% (loosest)
    }
}


def load_settings(market: Optional[str] = None) -> Dict[str, Any]:
    """Load gate settings. If market is given, merge per-market overrides on top of globals."""
    # 1. Load global defaults from file
    try:
        with open(_SETTINGS_FILE) as f:
            data = json.load(f)
        for gate, defaults in _DEFAULT_SETTINGS["gates"].items():
            data.setdefault("gates", {}).setdefault(gate, defaults)
    except FileNotFoundError:
        _save_settings(_DEFAULT_SETTINGS)
        data = {k: dict(v) if isinstance(v, dict) else v
                for k, v in _DEFAULT_SETTINGS.items()}
        data["gates"] = {g: dict(cfg) for g, cfg in _DEFAULT_SETTINGS["gates"].items()}
    except Exception:
        data = {k: dict(v) if isinstance(v, dict) else v
                for k, v in _DEFAULT_SETTINGS.items()}
        data["gates"] = {g: dict(cfg) for g, cfg in _DEFAULT_SETTINGS["gates"].items()}

    if not market:
        return data

    # 2. Overlay per-market gate tightness from market_state.config
    try:
        from core.db import db_cursor
        with db_cursor() as (_, cur):
            cur.execute("SELECT config FROM market_state WHERE market = ?", (market,))
            row = cur.fetchone()
        if row and row[0]:
            cfg = json.loads(row[0])
            market_gates = cfg.get("gates", {})
            for gate_name, overrides in market_gates.items():
                if gate_name in data["gates"]:
                    data["gates"][gate_name] = {**data["gates"][gate_name], **overrides}
    except Exception:
        pass

    return data


def _save_settings(settings: Dict[str, Any]) -> None:
    """Save global gate settings to file."""
    try:
        with open(_SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


def save_market_gate_settings(market: str, gate_overrides: Dict[str, Dict]) -> None:
    """Persist per-market gate tightness overrides into market_state.config."""
    from core.db import db_cursor
    with db_cursor() as (_, cur):
        cur.execute("SELECT config FROM market_state WHERE market = ?", (market,))
        row = cur.fetchone()
        cfg: dict = {}
        if row and row[0]:
            try:
                cfg = json.loads(row[0])
            except Exception:
                cfg = {}
        cfg["gates"] = {**cfg.get("gates", {}), **gate_overrides}
        cur.execute(
            "UPDATE market_state SET config = ?, updated_at = CURRENT_TIMESTAMP WHERE market = ?",
            (json.dumps(cfg), market),
        )


def update_gate_setting(gate_name: str, tightness: float, range_: Optional[float] = None,
                        market: Optional[str] = None) -> Dict[str, Any]:
    """Update a gate's tightness. If market given, updates per-market override; else updates global."""
    gate_name = gate_name.upper()
    if gate_name not in _DEFAULT_SETTINGS["gates"]:
        raise KeyError(f"Unknown gate: {gate_name}")
    tightness = max(0.0, min(1.0, tightness))

    if market:
        overrides: Dict[str, Dict] = {gate_name: {"tightness": tightness}}
        if range_ is not None:
            overrides[gate_name]["range"] = max(0.0, range_)
        save_market_gate_settings(market, overrides)
    else:
        settings = load_settings()
        settings["gates"][gate_name]["tightness"] = tightness
        if range_ is not None:
            settings["gates"][gate_name]["range"] = max(0.0, range_)
        _save_settings(settings)

    return load_settings(market)


# ── Data types ────────────────────────────────────────────────────────────────

class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"   # gate disabled / not applicable


@dataclass
class GateResult:
    gate: str
    status: GateStatus
    reason: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status in (GateStatus.PASS, GateStatus.SKIP)


@dataclass
class GateContext:
    """All inputs a gate may need. Unused fields are simply ignored."""
    # Timeframe direction values: +1 up, -1 down, 0 neutral
    timeframes: Dict[str, int] = field(default_factory=dict)   # {"5m": 1, "15m": 1, ...}
    wps: float = 0.0
    confidence: float = 0.0
    regime: str = "NEUTRAL"
    alignment: int = 0       # count of aligned timeframes
    # Health / connectivity
    api_ok: bool = True
    data_feed_ok: bool = True
    latency_ms: float = 0.0
    # Risk inputs
    open_trade_count: int = 0
    max_concurrent: int = 100
    stop_loss_pct: float = 2.0
    trailing_stop_pct: float = 1.5
    daily_loss_pct: float = 0.0   # realised loss today as % of kitty
    daily_loss_limit_pct: float = 10.0


# ── Base gate ─────────────────────────────────────────────────────────────────

class Gate:
    name: str = "GATE"
    # Base threshold before any slider adjustment.
    # Subclasses set this to a domain-appropriate value.
    base_threshold: float = 0.0

    def __init__(self, settings: Dict[str, Any]):
        cfg = settings["gates"].get(self.name, {})
        self.tightness: float = cfg.get("tightness", 0.5)
        self.range: float = cfg.get("range", 0.0)

    @property
    def threshold(self) -> float:
        return self.base_threshold + (self.tightness * self.range)

    def evaluate(self, ctx: GateContext) -> GateResult:  # pragma: no cover
        raise NotImplementedError


# ── Gate implementations ──────────────────────────────────────────────────────

class HlthGate(Gate):
    """HLTH — Is the system healthy enough to trade?"""
    name = "HLTH"
    base_threshold = 0.0   # HLTH is binary; tightness has no range by default

    def evaluate(self, ctx: GateContext) -> GateResult:
        if not ctx.api_ok:
            return GateResult("HLTH", GateStatus.FAIL, "API heartbeat failed")
        if not ctx.data_feed_ok:
            return GateResult("HLTH", GateStatus.FAIL, "Data feed heartbeat failed")
        # Latency threshold: base 500ms, slider can tighten toward 0
        max_latency = 500.0 - (self.tightness * self.range * 500.0)
        if ctx.latency_ms > max_latency and max_latency > 0:
            return GateResult("HLTH", GateStatus.FAIL,
                              f"Latency {ctx.latency_ms:.0f}ms > {max_latency:.0f}ms",
                              {"latency_ms": ctx.latency_ms})
        return GateResult("HLTH", GateStatus.PASS)


class Time4Gate(Gate):
    """TIME4 — Are all (or N of 4) timeframes aligned?"""
    name = "TIME4"
    base_threshold = 0.0   # base required TFs; tightness * range adds to it

    def evaluate(self, ctx: GateContext) -> GateResult:
        tf = ctx.timeframes
        vals = [tf.get("5m", 0), tf.get("15m", 0), tf.get("30m", 0), tf.get("60m", 0)]

        up   = vals.count(1)
        down = vals.count(-1)

        # required = 4 at tightness=1, approaches 2 at tightness=0 (range=1)
        required = int(round(2 + self.tightness * self.range * 2))
        required = max(2, min(4, required))

        if up >= required:
            return GateResult("TIME4", GateStatus.PASS, f"{up}/4 up ≥ {required}",
                              {"vals": vals, "required": required})
        if down >= required:
            return GateResult("TIME4", GateStatus.PASS, f"{down}/4 down ≥ {required}",
                              {"vals": vals, "required": required})

        dominant = max(up, down)
        return GateResult("TIME4", GateStatus.FAIL,
                          f"Best alignment {dominant}/4 < required {required}",
                          {"vals": vals, "required": required})


class TrendingGate(Gate):
    """TRENDING — Is the macro trend strong enough?"""
    name = "TRENDING"
    # Base: alignment must be ≥ 1. Slider tightens.
    base_threshold = 1.0

    def evaluate(self, ctx: GateContext) -> GateResult:
        required = self.threshold   # base 1.0, tightness shifts it up
        actual = abs(ctx.alignment)

        # At tightness=0 (default), allow any regime with ≥1 alignment.
        # Only block choppy/neutral when tightness > 0 (user explicitly tightened).
        regime_upper = ctx.regime.upper()
        if self.tightness > 0 and ("CHOPPY" in regime_upper or regime_upper == "NEUTRAL"):
            return GateResult("TRENDING", GateStatus.FAIL,
                              f"Regime {ctx.regime} disqualified (tightness={self.tightness:.2f})")

        if actual < required:
            return GateResult("TRENDING", GateStatus.FAIL,
                              f"Alignment {actual} < required {required:.2f}",
                              {"alignment": ctx.alignment, "regime": ctx.regime})

        return GateResult("TRENDING", GateStatus.PASS,
                          f"Alignment {actual} ≥ {required:.2f} | {ctx.regime}")


class WpsGate(Gate):
    """WPS — Is the market showing real pressure?"""
    name = "WPS"
    # Base absolute WPS threshold. Slider tightens.
    base_threshold = 10.0

    def evaluate(self, ctx: GateContext) -> GateResult:
        # Treat range as a multiplier on base so it scales naturally
        effective = self.base_threshold + (self.tightness * self.range * 100)
        actual = abs(ctx.wps)

        if actual < effective:
            return GateResult("WPS", GateStatus.FAIL,
                              f"|WPS| {actual:.1f} < required {effective:.1f}",
                              {"wps": ctx.wps, "required": effective})

        return GateResult("WPS", GateStatus.PASS,
                          f"|WPS| {actual:.1f} ≥ {effective:.1f}")


class ConfGate(Gate):
    """CONF — Is the signal strong enough to justify risk?"""
    name = "CONF"
    # Base confidence threshold (0–1 scale). Slider tightens.
    base_threshold = 0.20

    def evaluate(self, ctx: GateContext) -> GateResult:
        effective = self.base_threshold + (self.tightness * self.range)
        actual = ctx.confidence

        if actual < effective:
            return GateResult("CONF", GateStatus.FAIL,
                              f"Confidence {actual:.3f} < required {effective:.3f}",
                              {"confidence": actual, "required": effective})

        return GateResult("CONF", GateStatus.PASS,
                          f"Confidence {actual:.3f} ≥ {effective:.3f}")


class RiskGate(Gate):
    """RISK — Can we safely size and execute this trade?"""
    name = "RISK"
    base_threshold = 0.0

    def evaluate(self, ctx: GateContext) -> GateResult:
        # 1. Concurrent trade cap
        max_trades = int(ctx.max_concurrent * (1.0 - self.tightness * self.range))
        max_trades = max(1, max_trades)
        if ctx.open_trade_count >= max_trades:
            return GateResult("RISK", GateStatus.FAIL,
                              f"Open trades {ctx.open_trade_count} ≥ cap {max_trades}",
                              {"open": ctx.open_trade_count, "cap": max_trades})

        # 2. SL validity
        if ctx.stop_loss_pct <= 0:
            return GateResult("RISK", GateStatus.FAIL, "SL % must be > 0")

        # 3. Trailing stop must be ≤ SL
        if ctx.trailing_stop_pct > ctx.stop_loss_pct:
            return GateResult("RISK", GateStatus.FAIL,
                              f"TS {ctx.trailing_stop_pct}% > SL {ctx.stop_loss_pct}%")

        # 4. Daily loss limit (tighter slider → lower limit allowed)
        effective_limit = ctx.daily_loss_limit_pct * (1.0 - self.tightness * self.range)
        effective_limit = max(0.5, effective_limit)
        if ctx.daily_loss_pct >= effective_limit:
            return GateResult("RISK", GateStatus.FAIL,
                              f"Daily loss {ctx.daily_loss_pct:.1f}% ≥ limit {effective_limit:.1f}%",
                              {"daily_loss_pct": ctx.daily_loss_pct, "limit": effective_limit})

        return GateResult("RISK", GateStatus.PASS)


# ── Gate pipeline ─────────────────────────────────────────────────────────────

_GATE_ORDER = [HlthGate, Time4Gate, TrendingGate, WpsGate, ConfGate, RiskGate]


@dataclass
class PipelineResult:
    passed: bool
    results: list   # list[GateResult]
    failed_at: Optional[str] = None

    def summary(self) -> str:
        parts = []
        for r in self.results:
            icon = "✓" if r.passed else "✗"
            parts.append(f"{icon}{r.gate}")
        return " | ".join(parts)


def run_gates(ctx: GateContext, settings: Optional[Dict[str, Any]] = None,
              market: Optional[str] = None) -> PipelineResult:
    """Run all gates in order. Stops at first FAIL.
    If market is given, per-market gate overrides are applied on top of globals."""
    if settings is None:
        settings = load_settings(market)
    elif market:
        # Caller supplied settings but we still need per-market overrides applied
        settings = load_settings(market)

    results = []
    for GateClass in _GATE_ORDER:
        gate = GateClass(settings)
        result = gate.evaluate(ctx)
        results.append(result)
        if not result.passed:
            return PipelineResult(passed=False, results=results, failed_at=result.gate)

    return PipelineResult(passed=True, results=results)
