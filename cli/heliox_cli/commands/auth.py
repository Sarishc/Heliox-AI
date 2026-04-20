"""heliox auth — login, logout, whoami."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.prompt import Prompt

from heliox_cli import __version__
from heliox_cli.client import APIError, HelioxClient
from heliox_cli.config import (
    delete_api_key,
    get_api_url,
    get_api_key,
    load_config,
    save_api_key,
    save_config,
)
from heliox_cli.output import print_error, print_info, print_success, print_warning

app = typer.Typer(help="Authenticate with the Heliox API.")
console = Console()


@app.command()
def login(
    email: str = typer.Option("", "--email", "-e", help="Your Heliox account email."),
    api_url: str = typer.Option("", "--api-url", help="Override the API URL for this login."),
) -> None:
    """Log in and store credentials. Prompts for email and password."""
    url = (api_url or get_api_url()).rstrip("/")

    if not email:
        email = Prompt.ask("[cyan]Email[/cyan]")
    password = Prompt.ask("[cyan]Password[/cyan]", password=True)

    client = HelioxClient(api_url=url)
    try:
        body, cookies = client.login(email, password)
    except APIError as exc:
        print_error(str(exc))

    user = body.get("user", {})
    user_id = user.get("id", "")

    # Use the session cookie to fetch team context
    me_client = HelioxClient(api_url=url, cookies=cookies)
    try:
        me = me_client.whoami()
    except SystemExit:
        print_error("Login succeeded but could not fetch team info. Try again.")

    team_id = me.get("team_id", "")

    # Fetch team name
    team_name = ""
    if team_id:
        try:
            team = me_client.get_team(team_id)
            team_name = team.get("name", "")
        except Exception:
            pass

    # Create a persistent CLI API key via the session cookie
    try:
        raw_key = me_client.create_api_key(team_id, cookies)
    except APIError as exc:
        # If a CLI key already exists, look it up
        raw_key = ""
        print_warning(f"Could not create API key ({exc}). Existing key will be used if present.")

    # Persist
    if raw_key:
        save_api_key(raw_key)

    cfg = load_config()
    cfg.api_url = url
    cfg.team_id = team_id
    cfg.email = email
    cfg.team_name = team_name
    save_config(cfg)

    plan_str = ""
    try:
        plan_info = me_client.get_plan()
        plan_name = plan_info.get("plan", {}).get("name") or plan_info.get("plan_name", "")
        if plan_name:
            plan_str = f" — {plan_name} plan"
    except Exception:
        pass

    console.print()
    print_success(
        f"Logged in as [bold]{email}[/bold] "
        f"([cyan]{team_name or team_id}[/cyan]{plan_str})"
    )


@app.command()
def logout() -> None:
    """Clear stored credentials from this machine."""
    cfg = load_config()
    email = cfg.email or "unknown"

    delete_api_key()

    cfg.team_id = ""
    cfg.email = ""
    cfg.team_name = ""
    save_config(cfg)

    print_success(f"Logged out ({email}).")


@app.command()
def whoami() -> None:
    """Show the currently authenticated user and team."""
    api_url = get_api_url()
    api_key = get_api_key()

    if not api_key:
        print_error("Not logged in. Run `heliox auth login` first.")

    cfg = load_config()

    with HelioxClient(api_url=api_url, api_key=api_key) as client:
        try:
            me = client.whoami()
        except SystemExit:
            raise

    console.print()
    console.print(f"  [bold]Email[/bold]     {cfg.email or '—'}")
    console.print(f"  [bold]Team[/bold]      {cfg.team_name or me.get('team_id', '—')}")
    console.print(f"  [bold]Team ID[/bold]   {me.get('team_id', '—')}")
    console.print(f"  [bold]Role[/bold]      {me.get('role', '—')}")
    console.print(f"  [bold]API URL[/bold]   {api_url}")
    console.print()
