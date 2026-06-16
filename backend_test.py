#!/usr/bin/env python3
"""
Trading Engine Hub Backend API Testing
Tests all 50 engines and their APIs
"""
import requests
import sys
import json
from datetime import datetime

class TradingEngineAPITester:
    def __init__(self, base_url="https://trading-engine-hub-3.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, expected_fields=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)

            success = response.status_code == expected_status
            response_data = {}
            
            if success:
                try:
                    response_data = response.json()
                    
                    # Check expected fields if provided
                    if expected_fields:
                        for field in expected_fields:
                            if field not in response_data:
                                success = False
                                print(f"❌ Failed - Missing field: {field}")
                                break
                    
                    if success:
                        self.tests_passed += 1
                        print(f"✅ Passed - Status: {response.status_code}")
                        return True, response_data
                    
                except json.JSONDecodeError:
                    success = False
                    print(f"❌ Failed - Invalid JSON response")
            
            if not success:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                if response.text:
                    print(f"Response: {response.text[:200]}...")
                self.failed_tests.append({
                    "test": name,
                    "endpoint": endpoint,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "response": response.text[:200]
                })

            return success, response_data

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append({
                "test": name,
                "endpoint": endpoint,
                "error": str(e)
            })
            return False, {}

    def test_health_check(self):
        """Test health check returns 50 engines count"""
        success, data = self.run_test(
            "Health Check",
            "GET",
            "",
            200,
            expected_fields=["status", "engines", "broker_mode"]
        )
        
        if success and data.get("engines") == 50:
            print(f"✅ Health check shows {data['engines']} engines")
            return True
        elif success:
            print(f"❌ Expected 50 engines, got {data.get('engines')}")
            return False
        return False

    def test_engines_summary(self):
        """Test GET /api/engines/summary returns exactly 50 engines"""
        success, data = self.run_test(
            "Engines Summary",
            "GET",
            "engines/summary",
            200
        )
        
        if success:
            if isinstance(data, list) and len(data) == 50:
                print(f"✅ Found exactly 50 engines")
                
                # Check first engine has required fields
                if data:
                    engine = data[0]
                    required_fields = ["engine_id", "symbol", "type", "status", "pnl_today", "pnl_all_time"]
                    missing_fields = [f for f in required_fields if f not in engine]
                    if missing_fields:
                        print(f"❌ Missing fields in engine data: {missing_fields}")
                        return False
                    else:
                        print(f"✅ Engine data has all required fields")
                
                return True
            else:
                print(f"❌ Expected 50 engines, got {len(data) if isinstance(data, list) else 'non-list'}")
                return False
        return False

    def test_system_stats(self):
        """Test GET /api/stats returns system statistics"""
        success, data = self.run_test(
            "System Stats",
            "GET",
            "stats",
            200,
            expected_fields=["total_engines", "running", "paused", "stopped", "broker_mode"]
        )
        
        if success and data.get("total_engines") == 50:
            print(f"✅ Stats show {data['total_engines']} engines, broker_mode: {data.get('broker_mode')}")
            return True
        elif success:
            print(f"❌ Stats show {data.get('total_engines')} engines, expected 50")
            return False
        return False

    def test_start_all_engines(self):
        """Test POST /api/engines/start-all"""
        success, data = self.run_test(
            "Start All Engines",
            "POST",
            "engines/start-all",
            200
        )
        
        if success:
            print(f"✅ Start all command executed")
            return True
        return False

    def test_stop_all_engines(self):
        """Test POST /api/engines/stop-all"""
        success, data = self.run_test(
            "Stop All Engines",
            "POST",
            "engines/stop-all",
            200
        )
        
        if success:
            print(f"✅ Stop all command executed")
            return True
        return False

    def test_single_engine_operations(self):
        """Test single engine start/stop/reset operations"""
        engine_id = "market_01"
        
        # Test start single engine
        success1, _ = self.run_test(
            f"Start Engine {engine_id}",
            "POST",
            f"engines/{engine_id}/start",
            200
        )
        
        # Test stop single engine
        success2, _ = self.run_test(
            f"Stop Engine {engine_id}",
            "POST",
            f"engines/{engine_id}/stop",
            200
        )
        
        # Test reset single engine
        success3, _ = self.run_test(
            f"Reset Engine {engine_id}",
            "POST",
            f"engines/{engine_id}/reset",
            200
        )
        
        return success1 and success2 and success3

    def test_engine_detail(self):
        """Test GET /api/engines/{engine_id} returns detailed info"""
        engine_id = "market_01"
        success, data = self.run_test(
            f"Engine Detail {engine_id}",
            "GET",
            f"engines/{engine_id}",
            200,
            expected_fields=["engine_id", "symbol", "name", "type", "status", "config"]
        )
        
        if success and data.get("engine_id") == engine_id:
            print(f"✅ Engine detail for {engine_id} retrieved")
            return True
        return False

    def test_diagnostics(self):
        """Test GET /api/diagnostics/{engine_id}"""
        engine_id = "market_01"
        success, data = self.run_test(
            f"Engine Diagnostics {engine_id}",
            "GET",
            f"diagnostics/{engine_id}",
            200,
            expected_fields=["engine_id", "issues", "recommendations", "metrics"]
        )
        
        if success and data.get("engine_id") == engine_id:
            print(f"✅ Diagnostics for {engine_id} retrieved")
            return True
        return False

    def test_night_manager(self):
        """Test POST /api/night-manager/{engine_id}/run"""
        engine_id = "market_01"
        success, data = self.run_test(
            f"Night Manager {engine_id}",
            "POST",
            f"night-manager/{engine_id}/run",
            200
        )
        
        if success:
            print(f"✅ Night manager executed for {engine_id}")
            return True
        return False

    def test_alerts(self):
        """Test GET /api/alerts"""
        success, data = self.run_test(
            "Alerts",
            "GET",
            "alerts",
            200
        )
        
        if success and isinstance(data, list):
            print(f"✅ Alerts retrieved ({len(data)} alerts)")
            
            # Test per-engine alerts
            engine_id = "market_01"
            success2, data2 = self.run_test(
                f"Alerts for {engine_id}",
                "GET",
                f"alerts?engine_id={engine_id}",
                200
            )
            
            if success2:
                print(f"✅ Per-engine alerts retrieved for {engine_id}")
                return True
        return False

    def test_watchdog(self):
        """Test GET /api/watchdog"""
        success, data = self.run_test(
            "Watchdog Report",
            "GET",
            "watchdog",
            200,
            expected_fields=["timestamp", "total_engines", "running", "paused", "stopped"]
        )
        
        if success and data.get("total_engines") == 50:
            print(f"✅ Watchdog report shows {data['total_engines']} engines")
            return True
        return False

    def run_all_tests(self):
        """Run all backend API tests"""
        print("🚀 Starting Trading Engine Hub Backend API Tests")
        print("=" * 60)
        
        test_results = []
        
        # Core API tests
        test_results.append(self.test_health_check())
        test_results.append(self.test_engines_summary())
        test_results.append(self.test_system_stats())
        
        # Engine control tests
        test_results.append(self.test_start_all_engines())
        test_results.append(self.test_stop_all_engines())
        test_results.append(self.test_single_engine_operations())
        
        # Engine detail tests
        test_results.append(self.test_engine_detail())
        test_results.append(self.test_diagnostics())
        
        # Service tests
        test_results.append(self.test_night_manager())
        test_results.append(self.test_alerts())
        test_results.append(self.test_watchdog())
        
        # Print results
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.failed_tests:
            print(f"\n❌ Failed Tests ({len(self.failed_tests)}):")
            for failure in self.failed_tests:
                error_msg = failure.get('error', f"Expected {failure.get('expected')}, got {failure.get('actual')}")
                print(f"  - {failure['test']}: {error_msg}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"\n🎯 Success Rate: {success_rate:.1f}%")
        
        return success_rate >= 80  # Consider 80%+ as passing

def main():
    tester = TradingEngineAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())