"""Core domain models for the Paper Trading Engine.

Defines the order side enum, an immutable :class:`Fill` record, and a mutable
:class:`Position` that tracks a volume-weighted average entry price and the
realized PnL accumulated as the position is reduced.

Part of Paper Trading Engine by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Side(str, Enum):
    """Direction of an order or fill."""

    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        """Return ``+1`` for a buy and ``-1`` for a sell."""
        return 1 if self is Side.BUY else -1


class Fill(BaseModel):
    """An immutable record of a single executed order."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: Side
    qty: float = Field(gt=0.0)
    price: float = Field(gt=0.0)
    fee: float = Field(ge=0.0)

    @property
    def notional(self) -> float:
        """Gross trade value before fees (``qty * price``)."""
        return self.qty * self.price


class Position(BaseModel):
    """A net long position in a single symbol with average-cost accounting.

    Only long positions are tracked (sells reduce an existing long); selling
    more than is held raises an error in the engine before the position is
    touched, so ``qty`` never goes negative.
    """

    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0
    realized_pnl: float = 0.0

    def add(self, qty: float, price: float) -> None:
        """Increase the position, updating the volume-weighted average price.

        Args:
            qty: Quantity bought; must be positive.
            price: Execution price of the buy; must be positive.
        """
        if qty <= 0.0:
            raise ValueError("qty must be positive")
        if price <= 0.0:
            raise ValueError("price must be positive")
        total_cost = self.avg_price * self.qty + price * qty
        self.qty += qty
        self.avg_price = total_cost / self.qty

    def reduce(self, qty: float, price: float) -> float:
        """Reduce the position, realizing PnL against the average entry price.

        Args:
            qty: Quantity sold; must be positive and not exceed ``qty`` held.
            price: Execution price of the sell; must be positive.

        Returns:
            The realized PnL for this reduction (``(price - avg_price) * qty``).
        """
        if qty <= 0.0:
            raise ValueError("qty must be positive")
        if price <= 0.0:
            raise ValueError("price must be positive")
        if qty > self.qty + 1e-9:
            raise ValueError(f"cannot sell {qty} of {self.symbol}; only {self.qty} held")
        pnl = (price - self.avg_price) * qty
        self.qty -= qty
        self.realized_pnl += pnl
        if self.qty <= 1e-9:
            self.qty = 0.0
            self.avg_price = 0.0
        return pnl

    def market_value(self, mark_price: float) -> float:
        """Return the marked value of the position at ``mark_price``."""
        return self.qty * mark_price
