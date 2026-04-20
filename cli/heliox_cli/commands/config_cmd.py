"""heliox config — get, set, list."""

from __future__ import annotations

import typer
from rich.console import Console

from heliox_cli.config import load_config, save_config
from heliox_cli.output import as_json, print_error, print_success, print_table

app = typer.Typer(help="Manage CLI configuration (~/.heliox/config.json).")
console = Console()

_VALID_KEYS = {"api-url", "output", "team-id", "email"}
_VALID_OUTPUTS = {"table", "json", "csv"}


@app.command(name="set")
def set_config(
    key: str = typer.Argument(..., help=f"Config key: {', '.join(sorted(_VALID_KEYS))}"),
    value: str = typer.Argument(..., help="Value to set."),
) -> None:
    """Set a CLI configuration value."""
    cfg = load_config()

    match key:
        case "api-url":
            cfg.api_url = value.rstrip("/")
        case "output":
            if value not in _VALID_OUTPUTS:
                print_error(
                    f"Invalid output format '{value}'. "
                    f"Valid options: {', '.join(sorted(_VALID_OUTPUTS))}"
                )
            cfg.default_output = value
        case "team-id":
            cfg.team_id = value
        case "email":
            cfg.email = value
        case _:
            print_error(
                f"Unknown key '{key}'. "
                f"Valid keys: {', '.join(sorted(_VALID_KEYS))}"
            )

    save_config(cfg)
    print_success(f"[bold]{key}[/bold] = [cyan]{value}[/cyan]")


@app.command(name="get")
def get_config(
    key: str = typer.Argument(..., help="Config key to retrieve."),
) -> None:
    """Get a single CLI configuration value."""
    cfg = load_config()
    mapping = {
        "api-url": cfg.api_url,
        "output": cfg.default_output,
        "team-id": cfg.team_id,
        "email": cfg.email,
    }
    if key not in mapping:
        print_error(
            f"Unknown key '{key}'. "
            f"Valid keys: {', '.join(sorted(_VALID_KEYS))}"
        )
    console.print(mapping[key] or "")


@app.command(name="list")
def list_config(
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json."),
) -> None:
    """Show all current CLI configuration values."""
    cfg = load_config()
    data = {
        "api_url": cfg.api_url,
        "email": cfg.email or "(not logged in)",
        "team_id": cfg.team_id or "(not logged in)",
        "team_name": cfg.team_name or "(not logged in)",
        "default_output": cfg.default_output,
        "api_key_source": "keyring / HELIOX_API_KEY",
    }

    if output == "json":
        as_json(data)
        return

    rows = [[k, str(v)] for k, v in data.items()]
    print_table(["Key", "Value"], rows, title="Heliox CLI Config (~/.heliox/config.json)")
