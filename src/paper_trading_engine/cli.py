"""Command-line interface for Paper Trading Engine.

Subcommands:

* ``version`` — print the installed version.
* ``demo`` — run a sample order flow (market + limit) through one engine.
* ``report`` — run a two-account portfolio and print a realized/unrealized
  PnL report.
* ``book`` — demonstrate the limit order book matching helper with partial fills.

Part of Paper Trading Engine by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from paper_trading_engine import __version__
from paper_trading_engine.engine import PaperEngine
from paper_trading_engine.fees import PercentageFee, PercentageSlippage
from paper_trading_engine.models import Side
from paper_trading_engine.orderbook import OrderBook
from paper_trading_engine.portfolio import Portfolio

app = typer.Typer(add_completion=False, help="Paper Trading Engine - by Viprasol Tech.")
console = Console()


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"paper-trading-engine [bold cyan]{__version__}[/] - by Viprasol Tech")


@app.command()
def demo(
    starting_cash: float = typer.Option(10_000.0, help="Initial cash balance."),
    fee_rate: float = typer.Option(0.001, help="Proportional fee per fill (e.g. 0.001 = 10 bps)."),
    slippage: float = typer.Option(0.0, help="Per-fill slippage fraction on market orders."),
) -> None:
    """Run a sample order sequence and print positions, PnL, and equity."""
    engine = PaperEngine(
        starting_cash=starting_cash,
        fee_model=PercentageFee(fee_rate) if fee_rate > 0 else None,
        slippage_model=PercentageSlippage(slippage) if slippage > 0 else None,
    )

    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=110.0)
    engine.submit_market_order("AAPL", Side.SELL, qty=5.0, price=120.0)
    engine.submit_market_order("MSFT", Side.BUY, qty=4.0, price=300.0)
    # A marketable limit buy that fills immediately at the limit.
    engine.submit_limit_order("MSFT", Side.BUY, qty=2.0, limit_price=305.0, market_price=302.0)

    marks = {"AAPL": 130.0, "MSFT": 310.0}

    table = Table(title="Open positions")
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Avg entry", justify="right")
    table.add_column("Mark", justify="right")
    table.add_column("Value", justify="right")
    table.add_column("Unrealized", justify="right")
    for sym, pos in engine.positions().items():
        table.add_row(
            sym,
            f"{pos.qty:g}",
            f"${pos.avg_price:,.2f}",
            f"${marks[sym]:,.2f}",
            f"${pos.market_value(marks[sym]):,.2f}",
            f"${pos.unrealized_pnl(marks[sym]):,.2f}",
        )
    console.print(table)

    console.print(f"Fills:          {len(engine.fills)}")
    console.print(f"Cash:           [bold]${engine.cash:,.2f}[/]")
    console.print(f"Realized PnL:   [bold]${engine.realized_pnl():,.2f}[/]")
    console.print(f"Unrealized PnL: ${engine.unrealized_pnl(marks):,.2f}")
    console.print(f"Fees paid:      ${engine.fees_paid():,.2f}")
    console.print(
        f"Final equity:   [bold green]${engine.equity(marks):,.2f}[/]"
        f" (started ${starting_cash:,.2f})"
    )


@app.command()
def report() -> None:
    """Run a two-account portfolio and print a consolidated PnL report."""
    portfolio = Portfolio()
    momentum = portfolio.open_account("momentum", starting_cash=20_000.0, fee_rate=0.001)
    mean_rev = portfolio.open_account("mean-reversion", starting_cash=15_000.0, allow_short=True)

    momentum.submit_market_order("AAPL", Side.BUY, qty=50.0, price=100.0)
    momentum.submit_market_order("AAPL", Side.SELL, qty=20.0, price=115.0)
    mean_rev.submit_market_order("TSLA", Side.SELL, qty=10.0, price=250.0)  # opens a short

    marks = {"AAPL": 120.0, "TSLA": 240.0}
    rep = portfolio.report(marks)

    acct_table = Table(title="Accounts")
    for col in ("Account", "Cash", "Equity", "Realized", "Unrealized", "Fees", "Return %"):
        acct_table.add_column(col, justify="right" if col != "Account" else "left")
    for a in rep.accounts:
        acct_table.add_row(
            a.name,
            f"${a.cash:,.2f}",
            f"${a.equity:,.2f}",
            f"${a.realized_pnl:,.2f}",
            f"${a.unrealized_pnl:,.2f}",
            f"${a.fees_paid:,.2f}",
            f"{a.return_pct:+.2f}%",
        )
    console.print(acct_table)

    pos_table = Table(title="Positions")
    for col in ("Account", "Symbol", "Qty", "Avg", "Mark", "Unrealized"):
        pos_table.add_column(col, justify="right" if col not in ("Account", "Symbol") else "left")
    for p in rep.positions:
        pos_table.add_row(
            p.account,
            p.symbol,
            f"{p.qty:g}",
            f"${p.avg_price:,.2f}",
            f"${p.mark_price:,.2f}",
            f"${p.unrealized_pnl:,.2f}",
        )
    console.print(pos_table)

    console.print(f"Total equity:     [bold green]${rep.total_equity:,.2f}[/]")
    console.print(f"Total realized:   ${rep.total_realized_pnl:,.2f}")
    console.print(f"Total unrealized: ${rep.total_unrealized_pnl:,.2f}")
    console.print(f"Total return:     [bold]{rep.total_return_pct:+.2f}%[/]")


@app.command()
def book() -> None:
    """Demonstrate the limit order book matching helper with partial fills."""
    ob = OrderBook("AAPL")
    ob.add_limit(Side.SELL, price=101.0, qty=5.0, order_id="ask-1")
    ob.add_limit(Side.SELL, price=102.0, qty=10.0, order_id="ask-2")
    ob.add_limit(Side.BUY, price=99.0, qty=8.0, order_id="bid-1")

    console.print(
        f"Best bid: ${ob.best_bid():,.2f}  Best ask: ${ob.best_ask():,.2f}  "
        f"Spread: ${ob.spread():,.2f}  Mid: ${ob.mid_price():,.2f}"
    )

    # A marketable buy for 8 sweeps ask-1 (5) fully and ask-2 (3) partially.
    trades = ob.add_limit(Side.BUY, price=102.0, qty=8.0, order_id="taker-1")
    table = Table(title="Trades from incoming BUY 8 @ limit 102")
    for col in ("Price", "Qty", "Maker", "Taker"):
        table.add_column(col, justify="right" if col in ("Price", "Qty") else "left")
    for t in trades:
        table.add_row(
            f"${t.price:,.2f}", f"{t.qty:g}", t.maker_order_id or "-", t.taker_order_id or "-"
        )
    console.print(table)
    console.print(f"Remaining ask depth: {ob.depth(Side.SELL):g}")


if __name__ == "__main__":
    app()
