"""heliox jobs — list, show, top."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from heliox_cli.client import HelioxClient
from heliox_cli.config import get_api_key, get_api_url
from heliox_cli.output import as_json, print_error, print_table

app = typer.Typer(help="Inspect GPU jobs.")
console = Console()


def _require_auth() -> tuple[str, str]:
    api_url = get_api_url()
    api_key = get_api_key()
    if not api_key:
        print_error("Not logged in. Run `heliox auth login` first.")
    return api_url, api_key  # type: ignore[return-value]


def _status_badge(status: str) -> str:
    colours = {
        "running": "[bold green]●[/bold green]",
        "completed": "[green]✓[/green]",
        "failed": "[bold red]✗[/bold red]",
        "pending": "[yellow]○[/yellow]",
    }
    badge = colours.get(status.lower(), "")
    return f"{badge} {status}"


@app.command(name="list")
def list_jobs(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of jobs to return."),
    status: Optional[str] = typer.Option(
        None, "--status", "-s",
        help="Filter by status: running, completed, failed, pending."
    ),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json, csv."),
) -> None:
    """List recent GPU jobs."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        jobs = client.list_jobs(limit=limit, status=status)

    if output == "json":
        as_json(jobs)
        return

    if not jobs:
        console.print("[dim]No jobs found.[/dim]")
        return

    rows = []
    for j in jobs:
        job_id = str(j.get("id", ""))[:8]
        name = j.get("job_name") or j.get("name") or "—"
        st = j.get("status") or "—"
        provider = j.get("provider") or "—"
        gpu = j.get("gpu_type") or "—"
        cost = j.get("estimated_cost_usd") or j.get("cost_usd") or 0
        started = (j.get("start_time") or j.get("created_at") or "")[:10]

        if output != "csv":
            st = _status_badge(st)

        rows.append([job_id, name, st, provider, gpu, f"${float(cost):,.2f}", started])

    if output == "csv":
        print(",".join(["ID", "Name", "Status", "Provider", "GPU", "Est. Cost", "Started"]))
        for r in rows:
            print(",".join(r))
        return

    print_table(
        ["ID", "Name", "Status", "Provider", "GPU", "Est. Cost", "Started"],
        rows,
        title="GPU Jobs",
    )


@app.command()
def show(
    job_id: str = typer.Argument(..., help="Job ID to inspect."),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json."),
) -> None:
    """Show detailed information about a single job."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        job = client.get_job(job_id)

    if output == "json":
        as_json(job)
        return

    rows = [
        ["ID", job.get("id", "—")],
        ["Name", job.get("job_name") or job.get("name") or "—"],
        ["Status", _status_badge(job.get("status") or "—")],
        ["Provider", job.get("provider") or "—"],
        ["GPU Type", job.get("gpu_type") or "—"],
        ["GPU Count", str(job.get("gpu_count") or "—")],
        ["Est. Cost", f"${float(job.get('estimated_cost_usd') or 0):,.2f}"],
        ["Started", str(job.get("start_time") or "—")],
        ["Ended", str(job.get("end_time") or "running")],
        ["Team", str(job.get("team_id") or "—")],
    ]
    print_table(["Field", "Value"], rows, title=f"Job {str(job.get('id',''))[:8]}")


@app.command()
def top(
    by: str = typer.Option(
        "cost", "--by", "-b",
        help="Sort by: cost, duration, gpu-hours."
    ),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of jobs to show."),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json."),
) -> None:
    """Show the top most expensive (or longest) jobs."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        jobs = client.list_top_jobs(by=by, limit=limit)

    if output == "json":
        as_json(jobs)
        return

    if not jobs:
        console.print("[dim]No jobs found.[/dim]")
        return

    sort_key = {
        "cost": lambda j: float(j.get("estimated_cost_usd") or j.get("cost_usd") or 0),
        "gpu-hours": lambda j: float(j.get("gpu_hours") or 0),
        "duration": lambda j: float(j.get("duration_seconds") or 0),
    }.get(by, lambda j: float(j.get("estimated_cost_usd") or 0))

    jobs_sorted = sorted(jobs, key=sort_key, reverse=True)[:limit]

    rows = []
    for i, j in enumerate(jobs_sorted, 1):
        name = j.get("job_name") or j.get("name") or "—"
        cost = float(j.get("estimated_cost_usd") or j.get("cost_usd") or 0)
        gpu_hours = j.get("gpu_hours") or "—"
        provider = j.get("provider") or "—"
        gpu = j.get("gpu_type") or "—"
        rows.append([str(i), name[:40], provider, gpu,
                     f"${cost:,.2f}",
                     str(gpu_hours) if isinstance(gpu_hours, str) else f"{float(gpu_hours):,.1f}"])

    print_table(
        ["#", "Job Name", "Provider", "GPU", "Est. Cost", "GPU Hours"],
        rows,
        title=f"Top {limit} Jobs by {by.title()}",
    )
