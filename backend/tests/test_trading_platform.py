"""Backend tests for Trading Platform Command Center JSON-RPC endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trading-engine-hub-3.preview.emergentagent.com").rstrip("/")


def rpc_call(method, params=None):
    """Helper to make JSON-RPC calls and return the unwrapped result."""
    body = {"json": {"jsonrpc": "2.0", "id": 1, "method": method, "params": params if params is not None else []}}
    r = requests.post(f"{BASE_URL}/api/{method}", json=body, timeout=15)
    r.raise_for_status()
    data = r.json()
    assert "json" in data, f"Missing json envelope: {data}"
    inner = data["json"]
    assert inner.get("jsonrpc") == "2.0"
    assert "result" in inner, f"Missing result: {inner}"
    return inner["result"], r.status_code


# ── Health ────────────────────────────────────────────────────────────────────
class TestHealth:
    def test_health_get(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "timestamp" in data
        assert data.get("db") == "connected"

    def test_health_rpc(self):
        result, sc = rpc_call("health")
        assert sc == 200
        assert result["status"] == "ok"


# ── Stats ─────────────────────────────────────────────────────────────────────
class TestStats:
    def test_get_stats_shape(self):
        result, sc = rpc_call("getStats")
        assert sc == 200
        for key in ["total", "wins", "losses", "totalPnl", "todayWins", "todayLosses", "todayPnl", "winRate"]:
            assert key in result, f"Missing key {key} in stats: {result}"
        assert isinstance(result["wins"], int)
        assert isinstance(result["losses"], int)
        assert isinstance(result["winRate"], int)


# ── Trades ────────────────────────────────────────────────────────────────────
class TestTrades:
    def test_get_trades_returns_list(self):
        result, sc = rpc_call("getTrades")
        assert sc == 200
        assert isinstance(result, list)
        # PS: DB should have 28 trades per context
        if len(result) > 0:
            fields = {"id", "engine", "symbol", "side", "entry_price", "current_price",
                      "status", "pnl", "created_at", "size"}
            assert fields.issubset(set(result[0].keys())), f"Missing fields: {set(result[0].keys())}"


# ── Market State ──────────────────────────────────────────────────────────────
class TestMarketState:
    def test_get_market_state(self):
        result, sc = rpc_call("getMarketState")
        assert sc == 200
        for key in ["markets", "lifecycle", "kitty", "swarm", "status", "engines", "cryptoCoins"]:
            assert key in result, f"Missing {key}"
        assert result["status"] == "RUNNING"
        engines = result["engines"]
        for eng in ["equity", "crypto_scalp", "crypto_long"]:
            assert eng in engines
            assert "status" in engines[eng]
            assert "count" in engines[eng]

    def test_kitty_inside_market_state(self):
        result, _ = rpc_call("getMarketState")
        kitty = result["kitty"]
        assert kitty is not None
        for k in ["balance", "reserved", "available"]:
            assert k in kitty


# ── Kitty Summary ─────────────────────────────────────────────────────────────
class TestKitty:
    def test_get_kitty_summary(self):
        result, sc = rpc_call("getKittySummary")
        assert sc == 200
        for k in ["balance", "reserved", "available", "ladder", "max_exposure", "history"]:
            assert k in result
        assert isinstance(result["ladder"], list)
        assert result["ladder"] == [2, 4, 8, 16, 32]
        assert isinstance(result["history"], list)
        assert result["available"] == result["balance"] - result["reserved"]


# ── Risk Params ───────────────────────────────────────────────────────────────
class TestRiskParams:
    def test_get_risk_params(self):
        result, sc = rpc_call("getRiskParams")
        assert sc == 200
        for k in ["stop_loss_pct", "trailing_stop_pct", "base_trade_amount"]:
            assert k in result
            assert isinstance(result[k], (int, float))

    def test_set_risk_params_persists(self):
        # Get current values
        before, _ = rpc_call("getRiskParams")
        new_vals = {
            "stop_loss_pct": 2.5,
            "trailing_stop_pct": 1.8,
            "base_trade_amount": 3.00,
        }
        # Set
        result, _ = rpc_call("setRiskParams", [new_vals])
        assert result.get("ok") is True, f"Set failed: {result}"
        # Verify via GET
        after, _ = rpc_call("getRiskParams")
        assert after["stop_loss_pct"] == 2.5
        assert after["trailing_stop_pct"] == 1.8
        assert after["base_trade_amount"] == 3.00
        # Restore
        rpc_call("setRiskParams", [before])


# ── Trigger Cycle ─────────────────────────────────────────────────────────────
class TestTradingCycle:
    def test_run_trading_cycle(self):
        result, sc = rpc_call("runTradingCycle")
        assert sc == 200
        assert "ok" in result
        assert "timestamp" in result
        # Cycle might fail in test env, but we check shape


# ── Reset Market ──────────────────────────────────────────────────────────────
class TestResetMarket:
    def test_reset_market_valid(self):
        result, _ = rpc_call("resetMarket", ["TEST_MARKET"])
        assert result.get("ok") is True
        assert "SIM" in result.get("message", "")

    def test_reset_market_invalid(self):
        result, _ = rpc_call("resetMarket", [])
        assert result.get("ok") is False


# ── Close Trade ───────────────────────────────────────────────────────────────
class TestCloseTrade:
    def test_close_trade_invalid_id(self):
        result, _ = rpc_call("closeTradeNow", [999999])
        assert result.get("ok") is False
        assert "not found" in (result.get("error") or "").lower()

    def test_close_trade_open_trade(self):
        trades, _ = rpc_call("getTrades")
        open_trades = [t for t in trades if t.get("status") == "OPEN"]
        if not open_trades:
            pytest.skip("No open trades to close")
        trade_id = open_trades[0]["id"]
        result, _ = rpc_call("closeTradeNow", [trade_id])
        # Should succeed
        assert result.get("ok") is True, f"Close failed: {result}"


# ── cTrader ───────────────────────────────────────────────────────────────────
class TestCTrader:
    def test_ctrader_status(self):
        r = requests.get(f"{BASE_URL}/api/ctrader/status", timeout=10)
        assert r.status_code == 200
        data = r.json()
        # should have some connection status
        assert isinstance(data, dict)

    def test_ctrader_auth_url(self):
        r = requests.get(f"{BASE_URL}/api/ctrader/auth-url", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "url" in data
        assert data["url"].startswith("http")


# ── Extra endpoints ───────────────────────────────────────────────────────────
class TestExtras:
    def test_get_swarm_summary(self):
        result, _ = rpc_call("getSwarmSummary")
        assert "patterns" in result
        assert "active_gates" in result

    def test_get_system_events(self):
        result, _ = rpc_call("getSystemEvents")
        assert isinstance(result, list)

    def test_get_night_manager_log(self):
        result, _ = rpc_call("getNightManagerLog")
        assert isinstance(result, list)

    def test_unknown_method(self):
        body = {"json": {"jsonrpc": "2.0", "id": 1, "method": "nonexistent", "params": []}}
        r = requests.post(f"{BASE_URL}/api/nonexistent", json=body, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "error" in data["json"]["result"]
