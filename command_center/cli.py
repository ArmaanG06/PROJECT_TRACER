"""The `tracer` CLI.

The only module allowed to print. Everything under data_pulling logs, and the
CLI attaches a handler so those lines -- notably the failover switch warnings --
show up in the terminal alongside the tables.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from data_pulling import (
    TracerDataError,
    configure_logging,
    get_prices,
    get_provider,
    get_settings,
    load_universe,
    project_root,
    reset_providers,
    store,
)
from data_pulling.providers import PROVIDER_ORDER

from .registry import VALID_STATUSES, load_registry, registry_path, set_status

console = Console()

app = typer.Typer(help="Project Tracer command center.", no_args_is_help=True, add_completion=False)
data_app = typer.Typer(help="Data pipeline.", no_args_is_help=True)
algo_app = typer.Typer(help="Algo registry (config/strategies.yaml).", no_args_is_help=True)
app.add_typer(data_app, name="data")
app.add_typer(algo_app, name="algo")

_STATUS_STYLE = {"live": "bold red", "paper": "yellow", "dev": "cyan", "off": "dim"}


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Log at DEBUG level.")):
    # Windows consoles default to cp1252, which cannot encode the arrow in the
    # failover switch line and would crash the command mid-output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    configure_logging("DEBUG" if verbose else None)


@data_app.command("pull")
def data_pull(
    universe: Optional[str] = typer.Option(None, "--universe", "-u", help="Universe name, e.g. ROME."),
    symbols: Optional[List[str]] = typer.Option(None, "--symbols", help="Explicit tickers instead."),
    source: str = typer.Option("ibkr", "--source", "-s", help=" | ".join(PROVIDER_ORDER)),
    start: str = typer.Option("2010-01-01", "--start"),
    end: Optional[str] = typer.Option(None, "--end", help="Omit for latest available."),
    mode: str = typer.Option("strict", "--mode", "-m", help="strict | per_symbol"),
    refresh: bool = typer.Option(False, "--refresh", help="Ignore the cache."),
) -> None:
    """Pull a universe (or explicit symbols) into the cache."""
    tickers = [s.strip().upper() for v in (symbols or []) for s in v.split(",") if s.strip()]
    if not tickers:
        if not universe:
            console.print("[red]Give either --universe or --symbols.[/red]")
            raise typer.Exit(2)
        tickers = load_universe(universe)["symbol"].tolist()

    console.print(f"Pulling {len(tickers)} symbol(s) from [bold]{source}[/bold] ({mode}) from {start}…")
    try:
        prices = get_prices(tickers, start, end, source=source, mode=mode, refresh=refresh)
    except TracerDataError as exc:
        console.print(f"[red]{type(exc).__name__}:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        reset_providers()

    mix = prices.groupby("source")["symbol"].nunique().to_dict()
    console.print(
        f"[green]Done.[/green] {len(prices):,} rows, {prices['symbol'].nunique()} symbol(s), "
        f"{prices['date'].min().date()} → {prices['date'].max().date()}"
    )
    console.print("Source mix: " + ", ".join(f"{k}={v}" for k, v in sorted(mix.items())))


@data_app.command("status")
def data_status(
    universe: Optional[str] = typer.Option(None, "--universe", "-u", help="Restrict to a universe."),
) -> None:
    """Show what is in the cache: symbol, source, range, last pull, staleness."""
    manifest = store.status()
    if manifest.empty:
        console.print("[yellow]Cache is empty.[/yellow] Run `tracer data pull --universe ROME`.")
        return

    if universe:
        wanted = set(load_universe(universe)["symbol"])
        manifest = manifest[manifest["symbol"].isin(wanted)]
        if manifest.empty:
            console.print(f"[yellow]Nothing cached for {universe.upper()}.[/yellow]")
            return

    table = Table(title="Cached series", header_style="bold")
    for column in ("Symbol", "Source", "Start", "End", "Rows", "Last pull", "Stale"):
        table.add_column(column)
    for row in manifest.itertuples(index=False):
        stale = f"{row.stale_days}d" if row.stale_days <= 5 else f"[red]{row.stale_days}d[/red]"
        table.add_row(
            row.symbol, row.source, str(row.start), str(row.end),
            f"{row.rows:,}", row.pulled.strftime("%Y-%m-%d %H:%M"), stale,
        )
    console.print(table)

    mix = manifest.groupby("source")["symbol"].nunique().to_dict()
    console.print("Source mix: " + ", ".join(f"{k}={v}" for k, v in sorted(mix.items())))


@data_app.command("health")
def data_health() -> None:
    """Healthcheck all three providers."""
    settings = get_settings()
    table = Table(title="Provider health", header_style="bold")
    for column in ("Source", "Status", "Endpoint"):
        table.add_column(column, overflow="fold")

    for name in PROVIDER_ORDER:
        block = settings.provider(name)
        if name == "ibkr":
            endpoint = f"{block.get('host')}:{block.get('port')} clientId={block.get('client_id')}"
        elif name == "wrds":
            endpoint = f"wrds-pgdata.wharton.upenn.edu:9737 user={block.get('username') or '<pgpass>'}"
        else:
            endpoint = "Yahoo Finance (public)"
        try:
            ok = get_provider(name).healthcheck()
        except Exception:
            ok = False
        table.add_row(name, "[green]up[/green]" if ok else "[red]down[/red]", endpoint)

    reset_providers()
    console.print(table)


@algo_app.command("list")
def algo_list() -> None:
    """List every algo in the registry."""
    registry = load_registry()
    if not registry:
        console.print("[yellow]No strategies registered.[/yellow]")
        return

    table = Table(title="Algo registry", header_style="bold")
    for column in ("Name", "Universe", "Status", "Enabled", "Description"):
        table.add_column(column, overflow="fold")
    for strategy in registry.values():
        style = _STATUS_STYLE.get(strategy.status, "white")
        table.add_row(
            strategy.name, strategy.universe, f"[{style}]{strategy.status}[/{style}]",
            "yes" if strategy.enabled else "no", strategy.description,
        )
    console.print(table)
    console.print(f"[dim]{registry_path()}[/dim]")


@algo_app.command("set")
def algo_set(
    name: str = typer.Argument(..., help="Strategy name, e.g. ROME."),
    status: str = typer.Option(..., "--status", help=" | ".join(VALID_STATUSES)),
) -> None:
    """Set an algo's status. Edits config/strategies.yaml only."""
    try:
        updated = set_status(name.upper(), status.lower())
    except (KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2)
    style = _STATUS_STYLE.get(updated.status, "white")
    console.print(f"{updated.name} → [{style}]{updated.status}[/{style}]")


@app.command("dashboard")
def dashboard(port: int = typer.Option(8501, "--port")) -> None:
    """Launch the read-only Streamlit dashboard."""
    target = Path(__file__).with_name("dashboard.py")
    console.print(f"Starting dashboard on http://localhost:{port} …")
    try:
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(target),
             "--server.port", str(port), "--server.headless", "true"],
            cwd=project_root(), check=True,
        )
    except KeyboardInterrupt:
        console.print("\nDashboard stopped.")
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(exc.returncode)


if __name__ == "__main__":
    app()
