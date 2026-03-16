"""
Heliox AI Load Testing Suite
Simulates 100 concurrent users at 500 req/min target.
"""
import os
import random
import time
from locust import HttpUser, task, between, events
from datetime import datetime, timedelta

# Test configuration - use env vars for CI/load-test compatibility
API_KEY = os.environ.get("HELIOX_LOAD_TEST_API_KEY", "hlx_loadtest_placeholder")
ADMIN_API_KEY = os.environ.get("HELIOX_ADMIN_API_KEY") or os.environ.get("ADMIN_API_KEY") or ""
API_PREFIX = "/api/v1"

# Realistic model and team names
MODELS = [
    "gpt-4", "gpt-3.5-turbo", "claude-3-opus", "claude-3-sonnet",
    "llama-2-70b", "mixtral-8x7b", "gemini-pro", "command-r-plus"
]

TEAMS = [
    "engineering", "data-science", "ml-research", "product",
    "infrastructure", "analytics", "customer-success", "sales"
]

PROVIDERS = ["aws", "gcp", "azure", "lambda-labs", "runpod"]


# Target: 500 req/min with 100 users = 5 req/min per user = 1 req every 12 sec
# wait_time between(10, 14) yields ~12s avg → ~500 req/min total
LOAD_TEST_WAIT_MIN = int(os.environ.get("HELIOX_LOAD_WAIT_MIN", "10"))
LOAD_TEST_WAIT_MAX = int(os.environ.get("HELIOX_LOAD_WAIT_MAX", "14"))


class HelioxAPIUser(HttpUser):
    """
    Simulates a typical Heliox user
    """
    wait_time = between(LOAD_TEST_WAIT_MIN, LOAD_TEST_WAIT_MAX)  # ~500 req/min with 100 users
    
    def on_start(self):
        """Initialize user session"""
        self.headers = {
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        }
        self.team_id = None
        self.cost_snapshot_ids = []
    
    @task(10)
    def view_dashboard_costs(self):
        """Most common action: view costs"""
        with self.client.get(
            f"{API_PREFIX}/costs/",
            headers=self.headers,
            catch_response=True,
            name="GET /api/v1/costs/"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(8)
    def view_forecasts(self):
        """View GPU cost forecasts"""
        with self.client.get(
            f"{API_PREFIX}/forecast/usage",
            headers=self.headers,
            catch_response=True,
            name="GET /api/v1/forecast/usage"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(5)
    def view_teams(self):
        """View team context (me)"""
        with self.client.get(
            f"{API_PREFIX}/me",
            headers=self.headers,
            catch_response=True,
            name="GET /api/v1/me"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(3)
    def ingest_cost_data(self):
        """Simulate cost data ingestion"""
        from datetime import date
        today = date.today()
        payload = {
            "records": [
                {
                    "date": today.isoformat(),
                    "provider": random.choice(PROVIDERS),
                    "gpu_type": random.choice(["a100", "h100", "v100", "a10g"]),
                    "cost_usd": round(random.uniform(10, 500), 2)
                }
            ]
        }
        with self.client.post(
            f"{API_PREFIX}/ingest/cost",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="POST /api/v1/ingest/cost"
        ) as response:
            if response.status_code in [200, 201]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(4)
    def view_optimization_recommendations(self):
        """Check optimization opportunities"""
        with self.client.get(
            f"{API_PREFIX}/optimize/recommendations",
            headers=self.headers,
            catch_response=True,
            name="GET /api/v1/optimize/recommendations"
        ) as response:
            if response.status_code in [200, 404]:  # 404 acceptable if no data
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(2)
    def view_budgets(self):
        """View budget alerts"""
        with self.client.get(
            f"{API_PREFIX}/budgets/",
            headers=self.headers,
            catch_response=True,
            name="GET /api/v1/budgets/"
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(2)
    def view_integrations(self):
        """View integrations status"""
        with self.client.get(
            f"{API_PREFIX}/integrations",
            headers=self.headers,
            catch_response=True,
            name="GET /api/v1/integrations"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(1)
    def trigger_sync(self):
        """Simulate integration sync (expensive operation)"""
        response = self.client.get(
            f"{API_PREFIX}/integrations",
            headers=self.headers,
            catch_response=False
        )
        data = response.json() if response.status_code == 200 else {}
        connections = data.get("connections", []) if isinstance(data, dict) else []
        if connections:
            conn = connections[0] if isinstance(connections[0], dict) else {"id": str(connections[0])}
            integration_id = conn.get("id")
            if integration_id:
                with self.client.post(
                    f"{API_PREFIX}/integrations/{integration_id}/sync",
                    headers=self.headers,
                    catch_response=True,
                    name="POST /api/v1/integrations/{id}/sync"
                ) as sync_response:
                    if sync_response.status_code in [200, 202, 404]:
                        sync_response.success()
                    else:
                        sync_response.failure(f"Status {sync_response.status_code}")


class HelioxAdminUser(HttpUser):
    """
    Simulates admin operations (less frequent)
    """
    wait_time = between(12, 18)  # Slower than API users to keep ~500 req/min total
    weight = 1  # Less admin users
    
    def on_start(self):
        """Initialize admin session"""
        self.headers = {
            "X-API-Key": ADMIN_API_KEY,
            "Content-Type": "application/json"
        }
    
    @task(5)
    def view_all_teams(self):
        """Admin: view all teams"""
        with self.client.get(
            f"{API_PREFIX}/admin/teams",
            headers=self.headers,
            catch_response=True,
            name="GET /api/v1/admin/teams"
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(2)
    def view_system_stats(self):
        """Admin: health check (stats proxy)"""
        with self.client.get(
            f"{API_PREFIX}/admin/health",
            headers=self.headers,
            catch_response=True,
            name="GET /api/v1/admin/health"
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(1)
    def seed_demo_data(self):
        """Admin: seed demo data (creates load test key when requested)"""
        with self.client.post(
            f"{API_PREFIX}/admin/demo/seed?create_load_test_key=true",
            headers=self.headers,
            catch_response=True,
            name="POST /api/v1/admin/demo/seed"
        ) as response:
            if response.status_code in [200, 201]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")


# Locust events for custom metrics
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """Track slow requests"""
    if response_time > 800:
        print(f"⚠️  SLOW REQUEST: {name} took {response_time}ms (threshold: 800ms)")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start"""
    print("\n" + "="*80)
    print("🚀 HELIOX LOAD TEST STARTING")
    print("="*80)
    print(f"Target: {environment.host}")
    print(f"Users: {environment.parsed_options.num_users if hasattr(environment, 'parsed_options') else 'N/A'}")
    print(f"Spawn Rate: {environment.parsed_options.spawn_rate if hasattr(environment, 'parsed_options') else 'N/A'}")
    print("="*80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log test completion"""
    print("\n" + "="*80)
    print("✅ HELIOX LOAD TEST COMPLETED")
    print("="*80)
