"""Rich-based output formatting for the Heliox CLI."""

from __future__ import annotations

import json
import sys
from typing import Any, List, Optional

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from rich import box

# Heliox brand palette
BRAND_BLUE = "bright_cyan"
BRAND_TEAL = "cyan"
HEADER_STYLE = f"bold {BRAND_BLUE}"
POSITIVE = "green"
NEGATIVE = "red"
WARNING_COLOR = "yellow"

console = Console()
err_console = Console(stderr=True)

# Sparkline character set (8 levels, low → high)
_SPARKS = "▁▂▃▄▅▆▇█"


def print_table(
    headers: List[str],
    rows: List[List[Any]],
    title: Optional[str] = None,
    highlight_col: Optional[int] = None,
) -> None:
    """Render a Rich table with Heliox brand styling."""
    t = Table(
        title=title,
        title_style=HEADER_STYLE,
        box=box.SIMPLE_HEAVY,
        header_style=HEADER_STYLE,
        border_style=BRAND_TEAL,
        show_lines=False,
    )
    for h in headers:
        t.add_column(h, overflow="fold")
    for row in rows:
        str_row = [str(cell) for cell in row]
        t.add_row(*str_row)
    console.print(t)


def print_success(msg: str) -> None:
    console.print(f"[bold green]✓[/bold green] {msg}")


def print_error(msg: str, exit_code: int = 1) -> None:
    err_console.print(f"[bold red]✗[/bold red] {msg}")
    sys.exit(exit_code)


def print_warning(msg: str) -> None:
    console.print(f"[bold yellow]⚠[/bold yellow]  {msg}")


def print_info(msg: str) -> None:
    console.print(f"[{BRAND_BLUE}]ℹ[/{BRAND_BLUE}]  {msg}")


def print_json(data: Any) -> None:
    """Pretty-print JSON with syntax highlighting."""
    rendered = json.dumps(data, indent=2, default=str)
    console.print(Syntax(rendered, "json", theme="monokai"))


def print_cost(amount: float, budget: Optional[float] = None) -> str:
    """Format a dollar amount with optional budget colouring."""
    formatted = f"${amount:,.2f}"
    if budget is None:
        return formatted
    pct = amount / budget * 100 if budget else 0
    if pct >= 100:
        return f"[bold red]{formatted}[/bold red]"
    if pct >= 80:
        return f"[yellow]{formatted}[/yellow]"
    return f"[green]{formatted}[/green]"


def print_sparkline(values: List[float]) -> str:
    """Build an 8-level ASCII sparkline from a list of floats."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    spread = hi - lo or 1
    chars = [_SPARKS[min(7, int((v - lo) / spread * 8))] for v in values]
    return "".join(chars)


def format_delta(current: float, previous: float) -> str:
    """Return a coloured ±% string comparing two values."""
    if not previous:
        return ""
    pct = (current - previous) / abs(previous) * 100
    arrow = "↑" if pct >= 0 else "↓"
    color = NEGATIVE if pct >= 0 else POSITIVE
    sign = "+" if pct >= 0 else ""
    diff = current - previous
    return (
        f"[{color}]{arrow} {sign}{pct:.1f}% "
        f"({'+'if diff>=0 else ''}{diff:,.2f})[/{color}]"
    )


def as_json(data: Any) -> None:
    """Print raw JSON to stdout (no Rich markup) — for scripting."""
    print(json.dumps(data, indent=2, default=str))
