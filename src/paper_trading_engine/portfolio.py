"""Multi-account portfolio management and PnL reporting.

A :class:`Portfolio` groups several named :class:`~paper_trading_engine.engine.PaperEngine`
accounts so a strategy can run isolated books (e.g. per-strategy or per-desk)
and roll their results into a single realized + unrealized PnL report.

Part of Paper Trading Engine by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from paper_trading_engine.engine import PaperEngine


class PositionReport(BaseModel):
    """A single position line in a PnL report."""

    account: str
    symbol: str
    qty: float
    avg_price: float
    mark_price: float
    market_value: float
    realized_pnl: float
    unrealized_pnl: float


class AccountReport(BaseModel):
    """Per-account roll-up of cash, equity, and PnL."""

    name: str
    cash: float
    starting_cash: float
    positions_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    fees_paid: float
    return_pct: float


class PnLReport(BaseModel):
    """A portfolio-wide PnL report aggregated across accounts."""

    accounts: list[AccountReport]
    positions: list[PositionReport]
    total_equity: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_fees_paid: float
    total_return_pct: float


class Portfolio:
    """A collection of named, independently-funded trading accounts.

    Args:
        accounts: Optional initial mapping of account name to engine.
    """

    def __init__(self, accounts: Mapping[str, PaperEngine] | None = None) -> None:
        self._accounts: dict[str, PaperEngine] = dict(accounts or {})

    def open_account(
        self, name: str, starting_cash: float = 100_000.0, **kwargs: object
    ) -> PaperEngine:
        """Create and register a new account.

        Args:
            name: Unique account name; must not already exist.
            starting_cash: Initial cash for the account's engine.
            **kwargs: Forwarded to :class:`PaperEngine` (e.g. ``fee_rate``,
                ``allow_short``, ``fee_model``, ``slippage_model``).

        Returns:
            The newly created :class:`PaperEngine`.
        """
        if name in self._accounts:
            raise ValueError(f"account {name!r} already exists")
        engine = PaperEngine(starting_cash=starting_cash, **kwargs)  # type: ignore[arg-type]
        self._accounts[name] = engine
        return engine

    def add_account(self, name: str, engine: PaperEngine) -> None:
        """Register an existing engine under ``name``."""
        if name in self._accounts:
            raise ValueError(f"account {name!r} already exists")
        self._accounts[name] = engine

    def account(self, name: str) -> PaperEngine:
        """Return the engine registered under ``name``."""
        if name not in self._accounts:
            raise KeyError(f"no account named {name!r}")
        return self._accounts[name]

    def names(self) -> list[str]:
        """Return all account names in insertion order."""
        return list(self._accounts)

    def __len__(self) -> int:
        return len(self._accounts)

    def __contains__(self, name: object) -> bool:
        return name in self._accounts

    def total_equity(self, mark_prices: Mapping[str, float]) -> float:
        """Return summed equity across every account."""
        return sum(eng.equity(mark_prices) for eng in self._accounts.values())

    def total_realized_pnl(self) -> float:
        """Return summed realized PnL across every account."""
        return sum(eng.realized_pnl() for eng in self._accounts.values())

    def report(self, mark_prices: Mapping[str, float]) -> PnLReport:
        """Build a full realized + unrealized PnL report for all accounts.

        Args:
            mark_prices: Current price per symbol for every open position.

        Returns:
            A :class:`PnLReport` with per-account and per-position detail plus
            portfolio totals.
        """
        account_reports: list[AccountReport] = []
        position_reports: list[PositionReport] = []
        total_equity = 0.0
        total_realized = 0.0
        total_unrealized = 0.0
        total_fees = 0.0
        total_starting = 0.0

        for name, eng in self._accounts.items():
            realized = eng.realized_pnl()
            unrealized = eng.unrealized_pnl(mark_prices)
            equity = eng.equity(mark_prices)
            fees = eng.fees_paid()
            pos_value = eng.positions_value(mark_prices)
            ret = (
                (equity - eng.starting_cash) / eng.starting_cash * 100.0
                if eng.starting_cash > 0.0
                else 0.0
            )
            account_reports.append(
                AccountReport(
                    name=name,
                    cash=eng.cash,
                    starting_cash=eng.starting_cash,
                    positions_value=pos_value,
                    equity=equity,
                    realized_pnl=realized,
                    unrealized_pnl=unrealized,
                    fees_paid=fees,
                    return_pct=ret,
                )
            )
            for sym, pos in eng.positions().items():
                mark = mark_prices[sym]
                position_reports.append(
                    PositionReport(
                        account=name,
                        symbol=sym,
                        qty=pos.qty,
                        avg_price=pos.avg_price,
                        mark_price=mark,
                        market_value=pos.market_value(mark),
                        realized_pnl=pos.realized_pnl,
                        unrealized_pnl=pos.unrealized_pnl(mark),
                    )
                )
            total_equity += equity
            total_realized += realized
            total_unrealized += unrealized
            total_fees += fees
            total_starting += eng.starting_cash

        total_return = (
            (total_equity - total_starting) / total_starting * 100.0
            if total_starting > 0.0
            else 0.0
        )
        return PnLReport(
            accounts=account_reports,
            positions=position_reports,
            total_equity=total_equity,
            total_realized_pnl=total_realized,
            total_unrealized_pnl=total_unrealized,
            total_fees_paid=total_fees,
            total_return_pct=total_return,
        )
