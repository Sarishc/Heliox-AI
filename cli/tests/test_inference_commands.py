"""CLI inference command tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from heliox_cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr("heliox_cli.config._CONFIG_DIR", tmp_path / ".heliox")
    monkeypatch.setattr("heliox_cli.config._CONFIG_FILE", tmp_path / ".heliox" / "config.json")
    monkeypatch.setenv("HELIOX_API_KEY", "test-api-key-xxxx")
    monkeypatch.setenv("HELIOX_API_URL", "http://localhost:8000")
    yield


def test_inference_models_table(monkeypatch):
    """heliox inference models renders a table of tracked models."""
    models_payload = {
        "models": [
            {
                "model_name": "llama-3-70b",
                "serving_framework": "vllm",
                "cluster_name": "gpu-prod",
                "last_seen": "2026-04-20T10:00:00Z",
                "request_count_today": 1234,
                "avg_cost_per_1k_tokens": 0.0025,
            },
            {
                "model_name": "stable-diffusion-xl",
                "serving_framework": "custom",
                "cluster_name": None,
                "last_seen": "2026-04-19T08:00:00Z",
                "request_count_today": 567,
                "avg_cost_per_1k_tokens": None,
            },
        ]
    }

    with patch("heliox_cli.commands.inference.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.get_inference_models.return_value = models_payload

        result = runner.invoke(app, ["inference", "models"], env={"COLUMNS": "300"})

    assert result.exit_code == 0, result.output
    assert "llama-3-70b" in result.output
    assert "stable-diffusion-xl" in result.output
    assert "vllm" in result.output


def test_inference_top_shows_ranked_list(monkeypatch):
    """heliox inference top renders models ranked by total cost."""
    top_payload = {
        "models": [
            {
                "model_name": "llama-3-70b",
                "total_cost_usd": 1250.50,
                "total_requests": 50000,
                "avg_cost_per_1k_tokens": 0.0025,
                "p99_duration_ms": 3200.0,
            },
            {
                "model_name": "stable-diffusion-xl",
                "total_cost_usd": 430.20,
                "total_requests": 8500,
                "avg_cost_per_1k_tokens": None,
                "p99_duration_ms": 8500.0,
            },
        ]
    }

    with patch("heliox_cli.commands.inference.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.get_inference_top.return_value = top_payload

        result = runner.invoke(
            app, ["inference", "top", "--days", "7", "--limit", "10"],
            env={"COLUMNS": "300"},
        )

    assert result.exit_code == 0, result.output
    assert "llama-3-70b" in result.output
    assert "1250" in result.output or "$1250" in result.output


def test_inference_summary_filtered_by_model(monkeypatch):
    """heliox inference summary --model filters to a specific model."""
    summary_payload = {
        "model_name": "llama-3-70b",
        "days": 7,
        "granularity": "day",
        "summaries": [
            {
                "date": "2026-04-20",
                "model_name": "llama-3-70b",
                "request_count": 1500,
                "total_cost_usd": 37.50,
                "avg_cost_per_request": 0.000025,
                "avg_duration_ms": 1200.0,
            }
        ],
    }

    with patch("heliox_cli.commands.inference.HelioxClient") as MockClient:
        inst = MockClient.return_value.__enter__.return_value
        inst.get_inference_summary.return_value = summary_payload

        result = runner.invoke(
            app,
            ["inference", "summary", "--model", "llama-3-70b", "--days", "7"],
            env={"COLUMNS": "300"},
        )

    assert result.exit_code == 0, result.output
    assert "llama-3-70b" in result.output
    assert "2026-04-20" in result.output
    # Verify the client was called with the model filter
    inst.get_inference_summary.assert_called_once_with(days=7, model_name="llama-3-70b")
