"""
Heliox AI Load Testing Suite
Simulates 50 startups with realistic usage patterns
"""
import random
import time
from locust import HttpUser, task, between, events
from datetime import datetime, timedelta

# Test configuration
API_KEY = "hlx_jjN3llgYZZIHY63Qk0JdhqSNvra8JG4k4u3SAs_wKvY"  # Demo team API key
ADMIN_API_KEY = "heliox-admin-dev-key-change-in-production"

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


class HelioxAPIUser(HttpUser):
    """
    Simulates a typical Heliox user
    """
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
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
            "/api/costs/snapshots",
            headers=self.headers,
            catch_response=True,
            name="GET /api/costs/snapshots"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(8)
    def view_forecasts(self):
        """View GPU cost forecasts"""
        with self.client.get(
            "/api/forecasts",
            headers=self.headers,
            catch_response=True,
            name="GET /api/forecasts"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(5)
    def view_teams(self):
        """View team list"""
        with self.client.get(
            "/api/teams",
            headers=self.headers,
            catch_response=True,
            name="GET /api/teams"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(3)
    def ingest_cost_data(self):
        """Simulate cost data ingestion"""
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_cost": round(random.uniform(100, 5000), 2),
            "gpu_hours": round(random.uniform(10, 500), 2),
            "breakdown": {
                "model": random.choice(MODELS),
                "provider": random.choice(PROVIDERS),
                "region": random.choice(["us-east-1", "us-west-2", "eu-west-1"]),
                "team": random.choice(TEAMS)
            }
        }
        
        with self.client.post(
            "/api/costs/ingest",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="POST /api/costs/ingest"
        ) as response:
            if response.status_code in [200, 201]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(4)
    def view_optimization_recommendations(self):
        """Check optimization opportunities"""
        with self.client.get(
            "/api/optimizations/recommendations",
            headers=self.headers,
            catch_response=True,
            name="GET /api/optimizations/recommendations"
        ) as response:
            if response.status_code in [200, 404]:  # 404 acceptable if no data
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(2)
    def view_budgets(self):
        """View budget alerts"""
        with self.client.get(
            "/api/budgets",
            headers=self.headers,
            catch_response=True,
            name="GET /api/budgets"
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(2)
    def view_integrations(self):
        """View integrations status"""
        with self.client.get(
            "/api/integrations",
            headers=self.headers,
            catch_response=True,
            name="GET /api/integrations"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(1)
    def trigger_sync(self):
        """Simulate integration sync (expensive operation)"""
        # First get integrations
        response = self.client.get(
            "/api/integrations",
            headers=self.headers,
            catch_response=False
        )
        
        if response.status_code == 200 and response.json():
            integrations = response.json()
            if integrations:
                integration_id = integrations[0].get("id")
                with self.client.post(
                    f"/api/integrations/{integration_id}/sync",
                    headers=self.headers,
                    catch_response=True,
                    name="POST /api/integrations/{id}/sync"
                ) as sync_response:
                    if sync_response.status_code in [200, 202, 404]:
                        sync_response.success()
                    else:
                        sync_response.failure(f"Status {sync_response.status_code}")


class HelioxAdminUser(HttpUser):
    """
    Simulates admin operations (less frequent)
    """
    wait_time = between(5, 10)
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
            "/api/admin/teams",
            headers=self.headers,
            catch_response=True,
            name="GET /api/admin/teams"
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(2)
    def view_system_stats(self):
        """Admin: system statistics"""
        with self.client.get(
            "/api/admin/stats",
            headers=self.headers,
            catch_response=True,
            name="GET /api/admin/stats"
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(1)
    def seed_demo_data(self):
        """Admin: seed demo data"""
        payload = {
            "team_name": f"LoadTest-{random.randint(1000, 9999)}",
            "days_back": 30
        }
        
        with self.client.post(
            "/api/admin/demo/seed",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="POST /api/admin/demo/seed"
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
