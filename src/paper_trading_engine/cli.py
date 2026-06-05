"""Command-line interface for Paper Trading Engine.

``paper-trading-engine demo`` runs a fixed sequence of market orders through the
simulated engine and prints positions, realized PnL, fees, and final equity.

Part of Paper Trading Engine by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from paper_trading_engine import __version__
from paper_trading_engine.engine import PaperEngine
from paper_trading_engine.models import Side

app = typer.Typer(add_completion=False, help="Paper Trading Engine — by Viprasol Tech.")
console = Console()


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"paper-trading-engine [bold cyan]{__version__}[/] - by Viprasol Tech")


@app.command()
def demo(
    starting_cash: float = typer.Option(10_000.0, help="Initial cash balance."),
    fee_rate: float = typer.Option(0.001, help="Proportional fee per fill (e.g. 0.001 = 10 bps)."),
) -> None:
    """Run a sample order sequence and print positions, PnL, and equity."""
    engine = PaperEngine(starting_cash=starting_cash, fee_rate=fee_rate)

    # A simple, deterministic order flow across two symbols.
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=110.0)
    engine.submit_market_order("AAPL", Side.SELL, qty=5.0, price=120.0)
    engine.submit_market_order("MSFT", Side.BUY, qty=4.0, price=300.0)

    marks = {"AAPL": 130.0, "MSFT": 310.0}

    table = Table(title="Open positions")
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Avg entry", justify="right")
    table.add_column("Mark", justify="right")
    table.add_column("Value", justify="right")
    for sym, pos in engine.positions().items():
        table.add_row(
            sym,
            f"{pos.qty:g}",
            f"${pos.avg_price:,.2f}",
            f"${marks[sym]:,.2f}",
            f"${pos.market_value(marks[sym]):,.2f}",
        )
    console.print(table)

    console.print(f"Fills:        {len(engine.fills)}")
    console.print(f"Cash:         [bold]${engine.cash:,.2f}[/]")
    console.print(f"Realized PnL: [bold]${engine.realized_pnl():,.2f}[/]")
    console.print(f"Fees paid:    ${engine.fees_paid():,.2f}")
    console.print(
        f"Final equity: [bold green]${engine.equity(marks):,.2f}[/] (started ${starting_cash:,.2f})"
    )


if __name__ == "__main__":
    app()
