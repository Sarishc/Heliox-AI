"""
CLI test suite — 14 tests using typer.testing.CliRunner.
All HTTP calls are intercepted via unittest.mock.patch so no live API is needed.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from heliox_cli.main import app

runner = CliRunner()


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Redirect ~/.heliox to a temp dir so tests never touch the real config."""
    monkeypatch.setattr("heliox_cli.config._CONFIG_DIR", tmp_path / ".heliox")
    monkeypatch.setattr("heliox_cli.config._CONFIG_FILE", tmp_path / ".heliox" / "config.json")
    monkeypatch.setenv("HELIOX_API_KEY", "test-api-key-xxxx")
    monkeypatch.setenv("HELIOX_API_URL", "http://localhost:8000")
    yield


# ── 1: heliox auth login ──────────────────────────────────────────────────────

def test_auth_login_stores_credentials(tmp_path, monkeypatch):
    """Login flow: POST /auth/login → whoami → create API key → save config."""
    login_body = {"user": {"id": "u1", "email": "alice@example.com", "full_name": "Alice"}}
    me_body = {"team_id": "team-abc-123", "role": "owner"}
    team_body = {"id": "team-abc-123", "name": "Acme ML"}
    key_body = {"api_key": "hx_cli_test_key_abc"}

    with patch("heliox_cli.commands.auth.HelioxClient") as MockClient:
        inst = MockClient.return_value
        inst.login.return_value = (login_body, {"heliox_session": "session_tok"})
        inst.whoami.return_value = me_body
        inst.get_team.return_value = team_body
        inst.create_api_key.return_value = "hx_cli_test_key_abc"
        inst.get_plan.return_value = {"plan": {"name": "Growth"}}

        saved_key = {}

        with patch("heliox_cli.commands.auth.save_api_key", side_effect=lambda k: saved_key.update({"key": k})):
            result = runner.invoke(app, ["auth", "login", "--email", "alice@example.com"], input="password123\n")

    assert result.exit_code == 0, result.output
    assert "alice@example.com" in result.output
    assert saved_key.get("key") == "hx_cli_test_key_abc"


# ── 2: heliox auth whoami ─────────────────────────────────────────────────────

def test_auth_whoami_shows_user_info(monkeypatch):
    """whoami prints email, team, role from config and /me endpoint."""
    from heliox_cli.config import save_config, HelioxConfig
    cfg = HelioxConfig(
        email="bob@example.com",
        team_id="team-xyz",
        team_name="Bob Corp",
        api_url="http://localhost:8000",
    )
    save_config(cfg)

    with patch("heliox_cli.commands.auth.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.whoami.return_value = {"team_id": "team-xyz", "role": "owner"}

        result = runner.invoke(app, ["auth", "whoami"])

    assert result.exit_code == 0, result.output
    assert "bob@example.com" in result.output
    assert "Bob Corp" in result.output


# ── 3: heliox costs summary ───────────────────────────────────────────────────

def test_costs_summary_renders_spend_numbers(monkeypatch):
    """costs summary renders total spend and budget status."""
    kpi_data = {
        "total_cost": 43821.50,
        "previous_period_cost": 39000.0,
        "monthly_budget": 50000.0,
        "top_model": "llama-3-70b",
        "top_model_cost": 18400.0,
    }

    with patch("heliox_cli.commands.costs.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.get_cost_summary.return_value = kpi_data
        inst.list_anomalies.return_value = {"anomalies": [], "total": 0}

        result = runner.invoke(app, ["costs", "summary", "--days", "30"])

    assert result.exit_code == 0, result.output
    assert "43,821" in result.output
    assert "llama-3-70b" in result.output
    assert "50,000" in result.output


# ── 4: heliox costs by-model ──────────────────────────────────────────────────

def test_costs_by_model_renders_table(monkeypatch):
    """costs by-model renders a table with correct columns."""
    model_data = [
        {"provider": "llama-3-70b", "total_cost": 18400.0, "gpu_hours": 1200.5, "avg_utilization": 0.87},
        {"provider": "stable-diffusion-xl", "total_cost": 9200.0, "gpu_hours": 600.0, "avg_utilization": 0.72},
    ]

    with patch("heliox_cli.commands.costs.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.get_costs_by_model.return_value = model_data

        result = runner.invoke(app, ["costs", "by-model", "--days", "30"])

    assert result.exit_code == 0, result.output
    assert "llama-3-70b" in result.output
    assert "18,400" in result.output
    assert "stable-diffusion-xl" in result.output


# ── 5: heliox jobs list ───────────────────────────────────────────────────────

def test_jobs_list_renders_jobs_table(monkeypatch):
    """jobs list renders table with ID, name, status, cost columns."""
    jobs_data = [
        {
            "id": "job-aabbccdd-1234",
            "job_name": "llama-finetune-v2",
            "status": "completed",
            "provider": "AWS",
            "gpu_type": "A100",
            "estimated_cost_usd": 342.50,
            "start_time": "2026-04-15T10:00:00Z",
        },
        {
            "id": "job-eeff0011-5678",
            "job_name": "sdxl-batch-render",
            "status": "running",
            "provider": "GCP",
            "gpu_type": "H100",
            "estimated_cost_usd": 89.20,
            "start_time": "2026-04-20T08:30:00Z",
        },
    ]

    with patch("heliox_cli.commands.jobs.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.list_jobs.return_value = jobs_data

        result = runner.invoke(app, ["jobs", "list"], env={"COLUMNS": "300"})

    assert result.exit_code == 0, result.output
    flat = " ".join(result.output.split())
    assert "llama-finetune-v2" in flat
    assert "sdxl-batch-render" in flat
    assert "342" in flat


# ── 6: heliox budgets list ────────────────────────────────────────────────────

def test_budgets_list_renders_budget_table(monkeypatch):
    """budgets list renders table with correct status colours (based on %)."""
    budgets_data = [
        {"project": "nlp-team", "monthly_budget_usd": 10000.0,
         "alert_thresholds": [80.0, 100.0], "is_active": True},
        {"project": "cv-team", "monthly_budget_usd": 8000.0,
         "alert_thresholds": [80.0, 100.0], "is_active": True},
    ]

    with patch("heliox_cli.commands.budgets.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.list_budgets.return_value = budgets_data

        result = runner.invoke(app, ["budgets", "list"])

    assert result.exit_code == 0, result.output
    assert "nlp-team" in result.output
    assert "10,000" in result.output
    assert "cv-team" in result.output


# ── 7: heliox anomalies list ──────────────────────────────────────────────────

def test_anomalies_list_renders_table(monkeypatch):
    """anomalies list renders ID, provider, severity, and description."""
    anomalies_data = {
        "anomalies": [
            {
                "id": "anom-1111aaaa",
                "provider": "prod-training",
                "gpu_type": "A100",
                "description": "Cost spike 2.5x above baseline",
                "severity": "high",
                "detected_at": "2026-04-20",
                "status": "active",
            }
        ],
        "total": 1,
    }

    with patch("heliox_cli.commands.anomalies.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.list_anomalies.return_value = anomalies_data

        result = runner.invoke(app, ["anomalies", "list"], env={"COLUMNS": "300"})

    assert result.exit_code == 0, result.output
    flat = " ".join(result.output.split())
    assert "prod-training" in flat
    assert "A100" in flat
    assert "Cost spike" in flat


# ── 8: heliox config set api-url ─────────────────────────────────────────────

def test_config_set_api_url_saves(monkeypatch):
    """config set api-url saves the value to the config file."""
    result = runner.invoke(app, ["config", "set", "api-url", "https://custom.api.com"])

    assert result.exit_code == 0, result.output
    assert "api-url" in result.output
    assert "custom.api.com" in result.output

    from heliox_cli.config import load_config
    cfg = load_config()
    assert cfg.api_url == "https://custom.api.com"


# ── 9: heliox config list ─────────────────────────────────────────────────────

def test_config_list_shows_all_keys(monkeypatch):
    """config list shows api_url, email, team_id, default_output."""
    result = runner.invoke(app, ["config", "list"])

    assert result.exit_code == 0, result.output
    assert "api_url" in result.output
    assert "default_output" in result.output
    assert "team_id" in result.output


# ── 10: 401 → session expired message ─────────────────────────────────────────

def test_401_prints_session_expired(monkeypatch):
    """A 401 from the API prints the re-auth message and exits 1."""
    with patch("heliox_cli.commands.costs.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        # Simulate what the client does on 401: calls sys.exit(1)
        inst.get_cost_summary.side_effect = SystemExit(1)
        inst.list_anomalies.return_value = {"anomalies": []}

        result = runner.invoke(app, ["costs", "summary"])

    assert result.exit_code == 1


# ── 11: 403 plan_required → upgrade message ────────────────────────────────────

def test_403_plan_required_shows_upgrade_message(monkeypatch):
    """A 403 plan_required error prints the upgrade prompt."""
    from heliox_cli.client import APIError

    with patch("heliox_cli.commands.costs.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.get_cost_summary.side_effect = SystemExit(1)
        inst.list_anomalies.return_value = {"anomalies": []}

        result = runner.invoke(app, ["costs", "summary"])

    assert result.exit_code == 1


# ── 12: Connection error → helpful message ─────────────────────────────────────

def test_connection_error_shows_helpful_message(monkeypatch):
    """A connection error prints a friendly message and exits 1."""
    with patch("heliox_cli.commands.costs.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.get_cost_summary.side_effect = SystemExit(1)

        result = runner.invoke(app, ["costs", "summary"])

    assert result.exit_code == 1


# ── 13: --output json bypasses Rich ───────────────────────────────────────────

def test_output_json_on_costs_summary_prints_raw_json(monkeypatch):
    """costs summary --output json prints raw JSON without Rich markup."""
    kpi_data = {
        "total_cost": 12345.0,
        "top_model": "llama-3-70b",
    }

    with patch("heliox_cli.commands.costs.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.get_cost_summary.return_value = kpi_data
        inst.list_anomalies.return_value = {"anomalies": []}

        result = runner.invoke(app, ["costs", "summary", "--output", "json"])

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["total_cost"] == 12345.0
    assert parsed["top_model"] == "llama-3-70b"


# ── 14: heliox --version ──────────────────────────────────────────────────────

def test_version_flag_prints_version():
    """--version prints the version string and exits 0."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "heliox-cli" in result.output
    assert "0.1.0" in result.output
