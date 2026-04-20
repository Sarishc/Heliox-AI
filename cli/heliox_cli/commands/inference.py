"""heliox inference — per-model inference cost and latency commands."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from heliox_cli.client import HelioxClient
from heliox_cli.config import get_api_key, get_api_url
from heliox_cli.output import as_json, print_error, print_table

app = typer.Typer(help="Inspect per-model inference costs and latency.")
console = Console()

_OUTPUT_HELP = "Output format: table (default), json, csv."


def _require_auth() -> tuple[str, str]:
    api_url = get_api_url()
    api_key = get_api_key()
    if not api_key:
        print_error("Not logged in. Run `heliox auth login` first.")
    return api_url, api_key  # type: ignore[return-value]


@app.command()
def models(
    output: str = typer.Option("table", "--output", "-o", help=_OUTPUT_HELP),
) -> None:
    """List tracked inference models with today's request count and avg cost/1k tokens."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        data = client.get_inference_models()

    if output == "json":
        typer.echo(as_json(data))
        return

    rows = []
    for m in data if isinstance(data, list) else data.get("models", []):
        avg_cost = m.get("avg_cost_per_1k_tokens")
        cost_str = f"${avg_cost:.4f}" if avg_cost is not None else "—"
        rows.append([
            m.get("model_name", ""),
            m.get("serving_framework", "custom"),
            m.get("cluster_name") or "—",
            str(m.get("request_count_today", 0)),
            cost_str,
            m.get("last_seen", "")[:10] if m.get("last_seen") else "—",
        ])

    print_table(
        headers=["Model", "Framework", "Cluster", "Reqs Today", "$/1k Tokens", "Last Seen"],
        rows=rows,
        title="Inference Models",
    )


@app.command()
def summary(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Filter to a specific model."),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to summarise."),
    output: str = typer.Option("table", "--output", "-o", help=_OUTPUT_HELP),
) -> None:
    """Show daily cost and request volume per model over the past N days."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        data = client.get_inference_summary(days=days, model_name=model)

    if output == "json":
        typer.echo(as_json(data))
        return

    rows = []
    items = data if isinstance(data, list) else data.get("summaries", [])
    for row in items:
        rows.append([
            row.get("date", ""),
            row.get("model_name", ""),
            str(row.get("request_count", 0)),
            f"${row.get('total_cost_usd', 0):.4f}",
            f"${row.get('avg_cost_per_request', 0):.6f}",
            f"{row.get('avg_duration_ms', 0):.0f} ms",
        ])

    print_table(
        headers=["Date", "Model", "Requests", "Total Cost", "Avg/Req", "Avg Latency"],
        rows=rows,
        title=f"Inference Cost Summary — last {days} days",
    )


@app.command()
def top(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to consider."),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of models to show."),
    output: str = typer.Option("table", "--output", "-o", help=_OUTPUT_HELP),
) -> None:
    """Show the most expensive inference models by total cost."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        data = client.get_inference_top(days=days, limit=limit)

    if output == "json":
        typer.echo(as_json(data))
        return

    rows = []
    items = data if isinstance(data, list) else data.get("models", [])
    for i, m in enumerate(items, 1):
        avg_cost = m.get("avg_cost_per_1k_tokens")
        cost_str = f"${avg_cost:.4f}" if avg_cost is not None else "—"
        rows.append([
            str(i),
            m.get("model_name", ""),
            f"${m.get('total_cost_usd', 0):.4f}",
            str(m.get("total_requests", 0)),
            cost_str,
            f"{m.get('p99_duration_ms', 0):.0f} ms",
        ])

    print_table(
        headers=["#", "Model", "Total Cost", "Requests", "$/1k Tokens", "p99 Latency"],
        rows=rows,
        title=f"Top Inference Models by Cost — last {days} days",
    )
