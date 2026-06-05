"""Simulated paper-trading execution engine.

:class:`PaperEngine` fills market orders instantly at the supplied price,
debits/credits cash, applies a proportional fee, maintains per-symbol
:class:`~paper_trading_engine.models.Position` records with volume-weighted
average entry, and tracks realized PnL on sells. Equity is reported by marking
open positions to a caller-supplied price map.

Part of Paper Trading Engine by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from collections.abc import Mapping

from paper_trading_engine.models import Fill, Position, Side


class PaperEngine:
    """A cash-settled simulated execution engine for market orders.

    Args:
        starting_cash: Initial cash balance; must be non-negative.
        fee_rate: Proportional fee charged on the notional of every fill
            (e.g. ``0.001`` for 10 bps). Must be in ``[0, 1)``.
    """

    def __init__(self, starting_cash: float = 100_000.0, fee_rate: float = 0.0) -> None:
        if starting_cash < 0.0:
            raise ValueError("starting_cash must be non-negative")
        if not 0.0 <= fee_rate < 1.0:
            raise ValueError("fee_rate must be in [0, 1)")
        self.starting_cash: float = starting_cash
        self.cash: float = starting_cash
        self.fee_rate: float = fee_rate
        self._positions: dict[str, Position] = {}
        self.fills: list[Fill] = []

    def submit_market_order(self, symbol: str, side: Side, qty: float, price: float) -> Fill:
        """Fill a market order at ``price`` and update cash and positions.

        A buy debits ``qty * price + fee`` from cash and grows the position; a
        sell credits ``qty * price - fee`` to cash, reduces the position, and
        realizes PnL against the volume-weighted average entry price.

        Args:
            symbol: Instrument identifier (e.g. ``"AAPL"``).
            side: :class:`Side.BUY` or :class:`Side.SELL`.
            qty: Quantity to trade; must be positive.
            price: Execution price; must be positive.

        Returns:
            The recorded :class:`Fill`.

        Raises:
            ValueError: If ``qty``/``price`` are non-positive, a buy cannot be
                afforded, or a sell exceeds the held quantity.
        """
        if qty <= 0.0:
            raise ValueError("qty must be positive")
        if price <= 0.0:
            raise ValueError("price must be positive")

        notional = qty * price
        fee = notional * self.fee_rate
        position = self._positions.setdefault(symbol, Position(symbol=symbol))

        if side is Side.BUY:
            total_cost = notional + fee
            if total_cost > self.cash + 1e-9:
                raise ValueError(
                    f"insufficient cash for buy: need {total_cost:.2f}, have {self.cash:.2f}"
                )
            position.add(qty, price)
            self.cash -= total_cost
        else:
            position.reduce(qty, price)
            self.cash += notional - fee

        fill = Fill(symbol=symbol, side=side, qty=qty, price=price, fee=fee)
        self.fills.append(fill)
        return fill

    def position(self, symbol: str) -> Position:
        """Return the position for ``symbol`` (a flat position if untouched)."""
        return self._positions.get(symbol, Position(symbol=symbol))

    def positions(self) -> dict[str, Position]:
        """Return a mapping of all open (non-flat) positions by symbol."""
        return {sym: pos for sym, pos in self._positions.items() if pos.qty > 0.0}

    def realized_pnl(self) -> float:
        """Return total realized PnL across all symbols (sells only, pre-fee)."""
        return sum(pos.realized_pnl for pos in self._positions.values())

    def fees_paid(self) -> float:
        """Return the total fees charged across all fills."""
        return sum(fill.fee for fill in self.fills)

    def positions_value(self, mark_prices: Mapping[str, float]) -> float:
        """Return the marked value of all open positions.

        Args:
            mark_prices: Current price per symbol. Symbols with a non-zero
                position but no mark price raise :class:`KeyError`.
        """
        total = 0.0
        for sym, pos in self._positions.items():
            if pos.qty <= 0.0:
                continue
            if sym not in mark_prices:
                raise KeyError(f"no mark price supplied for open position {sym!r}")
            total += pos.market_value(mark_prices[sym])
        return total

    def equity(self, mark_prices: Mapping[str, float]) -> float:
        """Return total account equity: cash plus marked open positions.

        Args:
            mark_prices: Current price per symbol with an open position.
        """
        return self.cash + self.positions_value(mark_prices)
