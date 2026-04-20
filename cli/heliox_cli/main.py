"""heliox — GPU cost visibility for ML infrastructure teams."""

from __future__ import annotations

from typing import Optional

import typer

from heliox_cli import __version__
from heliox_cli.commands import auth, costs, jobs, budgets, anomalies, agent, config_cmd, inference

app = typer.Typer(
    name="heliox",
    help="GPU cost visibility and optimization for ML infrastructure teams.",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── Sub-command groups ────────────────────────────────────────────────────────
app.add_typer(auth.app,        name="auth",       help="Authenticate with the Heliox API.")
app.add_typer(costs.app,       name="costs",      help="Query GPU cost data.")
app.add_typer(jobs.app,        name="jobs",       help="Inspect GPU jobs.")
app.add_typer(budgets.app,     name="budgets",    help="Manage GPU spend budgets.")
app.add_typer(anomalies.app,   name="anomalies",  help="View and manage cost anomalies.")
app.add_typer(agent.app,       name="agent",      help="Deploy and manage the GPU agent DaemonSet.")
app.add_typer(config_cmd.app,  name="config",     help="Manage CLI configuration.")
app.add_typer(inference.app,   name="inference",  help="Inspect per-model inference costs.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"heliox-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        help="Show the CLI version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """
    [bold cyan]heliox[/bold cyan] — GPU cost visibility for ML infrastructure teams.

    Get started in 60 seconds:

      [dim]$ heliox auth login[/dim]
      [dim]$ heliox costs summary[/dim]
      [dim]$ heliox agent deploy[/dim]

    Documentation: [link=https://docs.heliox.ai/cli]https://docs.heliox.ai/cli[/link]
    """
