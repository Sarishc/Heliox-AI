"""heliox costs — summary, by-model, by-team, history."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from heliox_cli.client import HelioxClient
from heliox_cli.config import get_api_key, get_api_url
from heliox_cli.output import (
    as_json,
    format_delta,
    print_error,
    print_sparkline,
    print_table,
    print_warning,
)

app = typer.Typer(help="Query GPU cost data.")
console = Console()

_OUTPUT_HELP = "Output format: table (default), json, csv."


def _require_auth() -> tuple[str, str]:
    api_url = get_api_url()
    api_key = get_api_key()
    if not api_key:
        print_error("Not logged in. Run `heliox auth login` first.")
    return api_url, api_key  # type: ignore[return-value]


@app.command()
def summary(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to summarise."),
    output: str = typer.Option("table", "--output", "-o", help=_OUTPUT_HELP),
) -> None:
    """Show total GPU spend, budget status, and top model for the period."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        data = client.get_cost_summary(days=days)
        try:
            anomalies = client.list_anomalies(status="active")
            anomaly_count = (
                anomalies.get("total", len(anomalies.get("anomalies", [])))
                if isinstance(anomalies, dict)
                else len(anomalies)
            )
        except Exception:
            anomaly_count = 0

    if output == "json":
        as_json(data)
        return

    total = data.get("total_cost", 0) or 0
    prev = data.get("previous_period_cost") or 0
    budget = data.get("monthly_budget") or data.get("budget_limit") or 0
    top_model = data.get("top_model") or data.get("top_provider") or "—"
    top_model_cost = data.get("top_model_cost", 0) or 0

    console.print()
    console.rule(f"[bold cyan]GPU Cost Summary — Last {days} days[/bold cyan]")
    console.print()

    rows = [
        ["Total spend", f"${total:,.2f}"],
    ]
    if prev:
        rows.append(["vs. last period", format_delta(total, prev)])
    if budget:
        pct = total / budget * 100
        status_icon = "🔴" if pct >= 100 else ("🟡" if pct >= 80 else "🟢")
        rows.append(["Budget status", f"{status_icon} {pct:.0f}% of ${budget:,.2f} limit"])
    rows.append(["Top model", f"{top_model} (${top_model_cost:,.2f})"])
    if anomaly_count:
        rows.append(["Anomalies", f"[bold red]{anomaly_count} active[/bold red]"])

    print_table(["Metric", "Value"], rows)

    if anomaly_count:
        console.print(
            "  [dim]Run [bold]heliox anomalies list[/bold] to see active anomalies.[/dim]\n"
        )


@app.command(name="by-model")
def by_model(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to include."),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of models to show."),
    output: str = typer.Option("table", "--output", "-o", help=_OUTPUT_HELP),
) -> None:
    """Show spend broken down by model / provider."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        rows_data = client.get_costs_by_model(days=days, limit=limit)

    if output == "json":
        as_json(rows_data)
        return

    if not rows_data:
        console.print("[dim]No cost data for the selected period.[/dim]")
        return

    rows = []
    for i, item in enumerate(rows_data, 1):
        model = item.get("provider") or item.get("model") or item.get("gpu_type") or "—"
        cost = item.get("total_cost") or item.get("cost_usd") or 0
        gpu_hours = item.get("gpu_hours") or "—"
        util = item.get("avg_utilization") or "—"
        if isinstance(util, float):
            util = f"{util:.1f}%"
        if isinstance(gpu_hours, float):
            gpu_hours = f"{gpu_hours:,.1f}"
        rows.append([str(i), model, f"${float(cost):,.2f}", str(gpu_hours), str(util)])

    if output == "csv":
        print(",".join(["#", "Model", "Spend", "GPU Hours", "Utilization"]))
        for r in rows:
            print(",".join(r))
        return

    print_table(
        ["#", "Model / Provider", "Spend", "GPU Hours", "Avg Utilization"],
        rows,
        title=f"Cost by Model — Last {days} days",
    )


@app.command(name="by-team")
def by_team(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to include."),
    output: str = typer.Option("table", "--output", "-o", help=_OUTPUT_HELP),
) -> None:
    """Show spend broken down by sub-team / project."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        rows_data = client.get_costs_by_team(days=days)

    if output == "json":
        as_json(rows_data)
        return

    if not rows_data:
        console.print("[dim]No team cost data for the selected period.[/dim]")
        return

    total_all = sum(
        float(r.get("total_cost") or r.get("cost_usd") or 0) for r in rows_data
    )

    rows = []
    for item in rows_data:
        team = item.get("project") or item.get("team") or item.get("provider") or "—"
        cost = float(item.get("total_cost") or item.get("cost_usd") or 0)
        pct = cost / total_all * 100 if total_all else 0
        rows.append([team, f"${cost:,.2f}", f"{pct:.1f}%"])

    if output == "csv":
        print(",".join(["Team", "Spend", "% of Total"]))
        for r in rows:
            print(",".join(r))
        return

    print_table(
        ["Team / Project", "Spend", "% of Total"],
        rows,
        title=f"Cost by Team — Last {days} days",
    )


@app.command()
def history(
    days: int = typer.Option(90, "--days", "-d", help="Number of days of history to show."),
    output: str = typer.Option("table", "--output", "-o", help=_OUTPUT_HELP),
) -> None:
    """Show daily cost history with a sparkline trend."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        snapshots = client.get_cost_history(days=days)

    if output == "json":
        as_json(snapshots)
        return

    if not snapshots:
        console.print("[dim]No cost history data.[/dim]")
        return

    # Aggregate by date
    from collections import defaultdict
    daily: dict[str, float] = defaultdict(float)
    for s in snapshots:
        d = s.get("date", "")
        c = float(s.get("cost_usd") or s.get("total_cost") or 0)
        if d:
            daily[d] += c

    sorted_days = sorted(daily.items())
    values = [v for _, v in sorted_days]
    spark = print_sparkline(values)

    console.print()
    console.print(f"  [bold cyan]Trend (last {days}d):[/bold cyan] {spark}")
    console.print()

    if output == "csv":
        print("Date,Spend")
        for date, cost in sorted_days[-30:]:
            print(f"{date},{cost:.2f}")
        return

    recent = sorted_days[-30:]
    rows = [[d, f"${c:,.2f}"] for d, c in recent]
    print_table(["Date", "Daily Spend"], rows, title=f"Daily Cost History (last 30 of {days} days)")
