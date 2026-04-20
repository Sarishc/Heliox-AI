"""HTTP client wrapping all Heliox API calls."""

from __future__ import annotations

import sys
import time
from typing import Any, Optional

import httpx


class APIError(Exception):
    """Raised for non-retryable API errors."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class HelioxClient:
    """Thin httpx wrapper for the Heliox REST API."""

    def __init__(self, api_url: str, api_key: Optional[str] = None, cookies: Optional[dict] = None):
        self._base = api_url.rstrip("/") + "/api/v1"
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key
        self._client = httpx.Client(headers=headers, cookies=cookies or {}, timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HelioxClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── internal request helper ───────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base}{path}"
        try:
            resp = self._client.request(method, url, **kwargs)
        except httpx.ConnectError:
            base = self._base.replace("/api/v1", "")
            _error(
                f"Cannot connect to {base}. "
                "Check your connection or run `heliox config set api-url <url>`"
            )
        except httpx.TimeoutException:
            _error("Request timed out. The Heliox API may be slow — try again.")

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            _warn(f"Rate limited. Waiting {retry_after}s…")
            time.sleep(retry_after)
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.TransportError:
                _error("Connection failed on retry.")

        if resp.status_code == 401:
            _error("Session expired. Run `heliox auth login` to re-authenticate.")

        if resp.status_code == 403:
            try:
                body = resp.json()
            except Exception:
                body = {}
            if isinstance(body, dict):
                err = body.get("error") or (body.get("detail", {}) or {}).get("error", "")
                if err == "demo_mode":
                    _error(
                        "This action is disabled in the demo. "
                        "Sign up at https://app.heliox.ai/signup"
                    )
                if err == "plan_required":
                    plan = body.get("required_plan", "higher")
                    _error(
                        f"This feature requires the {plan} plan. "
                        "Run `heliox billing upgrade` to upgrade."
                    )
            _error(f"Permission denied: {resp.text}")

        if resp.status_code >= 500:
            try:
                msg = resp.json().get("detail", resp.text)
            except Exception:
                msg = resp.text
            _error(
                f"Heliox API error: {msg}. "
                "If this persists, check https://status.heliox.ai"
            )

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(str(detail), resp.status_code)

        if resp.status_code == 204:
            return {}

        return resp.json()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> tuple[dict, dict]:
        """POST /auth/login using OAuth2 form data. Returns (body, cookies)."""
        url = f"{self._base}/auth/login"
        try:
            resp = self._client.post(url, data={"username": email, "password": password})
        except httpx.ConnectError:
            base = self._base.replace("/api/v1", "")
            _error(f"Cannot connect to {base}.")
        if resp.status_code == 401:
            raise APIError("Incorrect email or password.", 401)
        if resp.status_code == 429:
            raise APIError("Too many login attempts. Try again later.", 429)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
                if isinstance(detail, dict):
                    detail = detail.get("message", str(detail))
            except Exception:
                detail = resp.text
            raise APIError(str(detail), resp.status_code)
        return resp.json(), dict(resp.cookies)

    def create_api_key(self, team_id: str, cookies: dict) -> str:
        """POST /teams/{team_id}/api-keys with session cookie. Returns raw key."""
        session_client = httpx.Client(
            headers={"Accept": "application/json"},
            cookies=cookies,
            timeout=30.0,
        )
        try:
            resp = session_client.post(
                f"{self._base}/teams/{team_id}/api-keys",
                json={"name": "CLI", "expires_days": 365},
            )
            if resp.status_code >= 400:
                raise APIError(f"Failed to create API key: {resp.text}", resp.status_code)
            return resp.json()["api_key"]
        finally:
            session_client.close()

    def whoami(self) -> dict:
        return self._request("GET", "/me")

    def get_team(self, team_id: str) -> dict:
        return self._request("GET", f"/teams/{team_id}")

    def list_team_api_keys(self, team_id: str) -> list:
        return self._request("GET", f"/teams/{team_id}/api-keys")

    # ── Costs ─────────────────────────────────────────────────────────────────

    def get_cost_summary(self, days: int = 30) -> dict:
        return self._request("GET", "/costs/kpis", params={"days": days})

    def get_costs_by_model(self, days: int = 30, limit: int = 10) -> list:
        return self._request("GET", "/costs/top-models", params={"days": days, "limit": limit})

    def get_costs_by_team(self, days: int = 30) -> list:
        return self._request("GET", "/costs/top-teams", params={"days": days})

    def get_cost_history(self, days: int = 90) -> list:
        return self._request("GET", "/costs/", params={"days": days, "limit": days * 6})

    # ── Jobs ──────────────────────────────────────────────────────────────────

    def list_jobs(self, limit: int = 20, status: Optional[str] = None) -> list:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        result = self._request("GET", "/jobs/", params=params)
        return result.get("jobs", result) if isinstance(result, dict) else result

    def get_job(self, job_id: str) -> dict:
        return self._request("GET", f"/jobs/{job_id}")

    def list_top_jobs(self, by: str = "cost", limit: int = 10) -> list:
        params = {"limit": limit, "sort_by": by}
        result = self._request("GET", "/jobs/", params=params)
        return result.get("jobs", result) if isinstance(result, dict) else result

    # ── Budgets ───────────────────────────────────────────────────────────────

    def list_budgets(self) -> list:
        return self._request("GET", "/budgets")

    def create_budget(self, project: str, amount: float, alert_threshold: float = 80.0) -> dict:
        return self._request("POST", "/budgets", json={
            "project": project,
            "monthly_budget_usd": amount,
            "alert_thresholds": [alert_threshold, 100.0],
        })

    def get_budget_status(self) -> list:
        return self._request("GET", "/budgets/status")

    # ── Anomalies ─────────────────────────────────────────────────────────────

    def list_anomalies(self, status: Optional[str] = "active") -> dict:
        params: dict[str, Any] = {}
        if status and status != "all":
            params["status"] = status
        return self._request("GET", "/anomalies", params=params)

    # ── Integrations ──────────────────────────────────────────────────────────

    def list_integrations(self) -> list:
        result = self._request("GET", "/integrations")
        return result.get("connections", result) if isinstance(result, dict) else result

    def trigger_sync(self, integration_id: str) -> dict:
        return self._request("POST", f"/integrations/{integration_id}/sync")

    # ── Inference Tracking ────────────────────────────────────────────────────

    def get_inference_models(self) -> dict:
        return self._request("GET", "/inference/models")

    def get_inference_summary(
        self, days: int = 7, model_name: Optional[str] = None
    ) -> dict:
        params: dict[str, Any] = {"days": days}
        if model_name:
            params["model_name"] = model_name
        return self._request("GET", "/inference/summary", params=params)

    def get_inference_top(self, days: int = 7, limit: int = 10) -> dict:
        return self._request(
            "GET", "/inference/cost-per-request",
            params={"days": days, "limit": limit},
        )

    # ── Plan / Billing ────────────────────────────────────────────────────────

    def get_plan(self) -> dict:
        return self._request("GET", "/billing/plan")


# ── helpers ───────────────────────────────────────────────────────────────────

def _error(msg: str) -> None:
    from rich.console import Console
    Console(stderr=True).print(f"[bold red]✗[/bold red] {msg}")
    sys.exit(1)


def _warn(msg: str) -> None:
    from rich.console import Console
    Console(stderr=True).print(f"[yellow]⚠[/yellow]  {msg}")
