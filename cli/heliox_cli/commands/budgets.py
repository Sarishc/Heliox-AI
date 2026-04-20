"""heliox budgets — list, set, status."""

from __future__ import annotations

import typer
from rich.console import Console

from heliox_cli.client import APIError, HelioxClient
from heliox_cli.config import get_api_key, get_api_url
from heliox_cli.output import as_json, print_error, print_success, print_table

app = typer.Typer(help="Manage GPU spend budgets.")
console = Console()


def _require_auth() -> tuple[str, str]:
    api_url = get_api_url()
    api_key = get_api_key()
    if not api_key:
        print_error("Not logged in. Run `heliox auth login` first.")
    return api_url, api_key  # type: ignore[return-value]


def _health_badge(pct: float) -> str:
    if pct >= 100:
        return "[bold red]● OVER BUDGET[/bold red]"
    if pct >= 90:
        return "[bold red]● 90%+ critical[/bold red]"
    if pct >= 80:
        return "[yellow]● 80%+ warning[/yellow]"
    return "[green]● healthy[/green]"


@app.command(name="list")
def list_budgets(
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json, csv."),
) -> None:
    """List all budget policies."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        budgets = client.list_budgets()

    if output == "json":
        as_json(budgets)
        return

    if not budgets:
        console.print("[dim]No budget policies configured.[/dim]")
        console.print("  Run [bold]heliox budgets set <project> <amount>[/bold] to create one.")
        return

    rows = []
    for b in budgets:
        project = b.get("project") or b.get("environment") or "org"
        limit = float(b.get("monthly_budget_usd") or 0)
        thresholds = b.get("alert_thresholds") or []
        active = "yes" if b.get("is_active", True) else "no"
        rows.append([
            project,
            f"${limit:,.2f}/mo",
            ", ".join(f"{t:.0f}%" for t in thresholds) if thresholds else "80%, 100%",
            active,
        ])

    if output == "csv":
        print(",".join(["Project", "Monthly Limit", "Alert Thresholds", "Active"]))
        for r in rows:
            print(",".join(r))
        return

    print_table(
        ["Project", "Monthly Limit", "Alert Thresholds", "Active"],
        rows,
        title="Budget Policies",
    )


@app.command(name="set")
def set_budget(
    project: str = typer.Argument(..., help="Project or team name to budget."),
    amount: float = typer.Argument(..., help="Monthly budget limit in USD."),
    threshold: float = typer.Option(
        80.0, "--threshold", "-t",
        help="Alert threshold percentage (default: 80)."
    ),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json."),
) -> None:
    """Set a monthly budget limit for a project or team."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        try:
            result = client.create_budget(project=project, amount=amount, alert_threshold=threshold)
        except APIError as exc:
            print_error(str(exc))

    if output == "json":
        as_json(result)
        return

    print_success(
        f"Budget set: [bold]{project}[/bold] → "
        f"[bold]${amount:,.2f}/month[/bold] "
        f"(alert at {threshold:.0f}%)"
    )


@app.command()
def status(
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json."),
) -> None:
    """Traffic-light view of all budget health."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        statuses = client.get_budget_status()

    if output == "json":
        as_json(statuses)
        return

    if not statuses:
        console.print("[dim]No budget data yet.[/dim]")
        return

    rows = []
    for s in statuses:
        project = s.get("project") or s.get("environment") or "org"
        limit = float(s.get("monthly_budget_usd") or s.get("budget_limit") or 0)
        spent = float(s.get("current_spend") or s.get("spent") or 0)
        pct = spent / limit * 100 if limit else 0
        badge = _health_badge(pct)
        rows.append([
            project,
            f"${spent:,.2f}",
            f"${limit:,.2f}",
            f"{pct:.1f}%",
            badge,
        ])

    print_table(
        ["Project", "Spent", "Limit", "Used %", "Health"],
        rows,
        title="Budget Status",
    )
