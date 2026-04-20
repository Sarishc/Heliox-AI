"""heliox anomalies — list, acknowledge."""

from __future__ import annotations

import typer
from rich.console import Console

from heliox_cli.client import APIError, HelioxClient
from heliox_cli.config import get_api_key, get_api_url
from heliox_cli.output import as_json, print_error, print_success, print_table

app = typer.Typer(help="View and manage detected cost anomalies.")
console = Console()


def _require_auth() -> tuple[str, str]:
    api_url = get_api_url()
    api_key = get_api_key()
    if not api_key:
        print_error("Not logged in. Run `heliox auth login` first.")
    return api_url, api_key  # type: ignore[return-value]


def _severity_badge(severity: str) -> str:
    s = (severity or "").lower()
    if s in ("high", "critical"):
        return f"[bold red]{severity}[/bold red]"
    if s == "medium":
        return f"[yellow]{severity}[/yellow]"
    return f"[green]{severity}[/green]"


@app.command(name="list")
def list_anomalies(
    status: str = typer.Option(
        "active", "--status", "-s",
        help="Filter by status: active, resolved, all."
    ),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json, csv."),
) -> None:
    """List detected cost and utilization anomalies."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        result = client.list_anomalies(status=status)

    anomalies = (
        result.get("anomalies", result)
        if isinstance(result, dict)
        else result
    )

    if output == "json":
        as_json(result)
        return

    if not anomalies:
        console.print(f"[dim]No {status} anomalies found.[/dim]")
        return

    rows = []
    for a in anomalies:
        aid = str(a.get("id", ""))[:8]
        provider = a.get("provider") or "—"
        gpu = a.get("gpu_type") or "—"
        desc = (a.get("description") or a.get("anomaly_type") or "—")[:60]
        sev = a.get("severity") or "medium"
        date = str(a.get("detected_at") or a.get("date") or "—")[:10]
        anom_status = a.get("status") or status

        if output != "csv":
            sev = _severity_badge(sev)

        rows.append([aid, provider, gpu, desc, sev, date, anom_status])

    if output == "csv":
        print(",".join(["ID", "Provider", "GPU", "Description", "Severity", "Date", "Status"]))
        for r in rows:
            print(",".join(r))
        return

    print_table(
        ["ID", "Provider", "GPU", "Description", "Severity", "Detected", "Status"],
        rows,
        title=f"Anomalies ({status})",
    )


@app.command()
def acknowledge(
    anomaly_id: str = typer.Argument(..., help="Anomaly ID to acknowledge."),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json."),
) -> None:
    """Acknowledge an anomaly (marks it as reviewed)."""
    api_url, api_key = _require_auth()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        try:
            # The anomalies endpoint is GET-only; use a PATCH/PUT if available
            result = client._request("PATCH", f"/anomalies/{anomaly_id}", json={"status": "acknowledged"})
        except (APIError, SystemExit) as exc:
            # Fall back: some deployments may not have a PATCH endpoint yet
            if isinstance(exc, APIError) and exc.status_code == 405:
                print_error(
                    "Acknowledge not supported by this API version. "
                    "Upgrade to Heliox API ≥ 1.1.0."
                )
            raise

    if output == "json":
        as_json(result)
        return

    print_success(f"Anomaly [bold]{anomaly_id}[/bold] acknowledged.")
