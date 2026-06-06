"""Core domain models for the Paper Trading Engine.

Defines the order side and type enums, an immutable :class:`Fill` record, an
:class:`Order` (which may be partially filled), and a mutable :class:`Position`
that tracks a signed quantity, a volume-weighted average entry price, and the
realized PnL accumulated as the position is reduced or flipped. Positions may be
long *or* short.

Part of Paper Trading Engine by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

import itertools
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

_order_ids = itertools.count(1)


def _next_order_id() -> str:
    """Return a process-unique, human-readable order identifier."""
    return f"ord-{next(_order_ids)}"


class Side(str, Enum):
    """Direction of an order or fill."""

    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        """Return ``+1`` for a buy and ``-1`` for a sell."""
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> Side:
        """Return the opposing side."""
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(str, Enum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """Lifecycle state of an order."""

    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Fill(BaseModel):
    """An immutable record of a single executed (possibly partial) order."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: Side
    qty: float = Field(gt=0.0)
    price: float = Field(gt=0.0)
    fee: float = Field(ge=0.0)
    order_id: str | None = None

    @property
    def notional(self) -> float:
        """Gross trade value before fees (``qty * price``)."""
        return self.qty * self.price


class Order(BaseModel):
    """A resting or in-flight order that may fill across several events.

    Market orders ignore ``limit_price``. Limit orders only fill at a price no
    worse than ``limit_price`` (at or below for buys, at or above for sells).
    """

    id: str = Field(default_factory=_next_order_id)
    symbol: str
    side: Side
    qty: float = Field(gt=0.0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = Field(default=None, gt=0.0)
    filled_qty: float = Field(default=0.0, ge=0.0)
    status: OrderStatus = OrderStatus.NEW

    @property
    def remaining(self) -> float:
        """Quantity still open on the order."""
        return max(self.qty - self.filled_qty, 0.0)

    @property
    def is_open(self) -> bool:
        """``True`` while the order can still take more fills."""
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    def accepts_price(self, price: float) -> bool:
        """Return whether ``price`` satisfies a limit order's constraint.

        Market orders accept any price.
        """
        if self.order_type is OrderType.MARKET or self.limit_price is None:
            return True
        if self.side is Side.BUY:
            return price <= self.limit_price + 1e-9
        return price >= self.limit_price - 1e-9

    def record_fill(self, qty: float) -> None:
        """Apply a fill of ``qty`` units and advance the order status.

        Args:
            qty: Quantity filled; must be positive and not exceed ``remaining``.
        """
        if qty <= 0.0:
            raise ValueError("fill qty must be positive")
        if qty > self.remaining + 1e-9:
            raise ValueError(f"fill {qty} exceeds remaining {self.remaining}")
        self.filled_qty += qty
        if self.remaining <= 1e-9:
            self.filled_qty = self.qty
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIALLY_FILLED


class Position(BaseModel):
    """A signed position in a single symbol with average-cost accounting.

    A positive :attr:`qty` is long, a negative :attr:`qty` is short, and zero is
    flat. :meth:`apply` handles every case — growing, reducing, closing, and
    flipping across zero — realizing PnL whenever exposure is reduced.
    """

    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0
    realized_pnl: float = 0.0

    @property
    def is_long(self) -> bool:
        """``True`` when the net quantity is positive."""
        return self.qty > 1e-9

    @property
    def is_short(self) -> bool:
        """``True`` when the net quantity is negative."""
        return self.qty < -1e-9

    @property
    def is_flat(self) -> bool:
        """``True`` when the position holds no exposure."""
        return abs(self.qty) <= 1e-9

    def apply(self, signed_qty: float, price: float) -> float:
        """Apply a signed trade (``+`` buy / ``-`` sell) and return realized PnL.

        Increasing exposure in the current direction updates the volume-weighted
        average entry. Reducing or closing exposure realizes PnL against that
        average. A trade larger than the open quantity in the opposite direction
        closes the position and re-opens it on the other side at ``price``.

        Args:
            signed_qty: Quantity with sign; positive buys, negative sells. Must
                be non-zero.
            price: Execution price; must be positive.

        Returns:
            The realized PnL booked by this trade (``0.0`` if only opening).
        """
        if signed_qty == 0.0:
            raise ValueError("signed_qty must be non-zero")
        if price <= 0.0:
            raise ValueError("price must be positive")

        same_direction = self.is_flat or (self.qty > 0) == (signed_qty > 0)
        if same_direction:
            total_cost = self.avg_price * abs(self.qty) + price * abs(signed_qty)
            self.qty += signed_qty
            self.avg_price = total_cost / abs(self.qty)
            return 0.0

        # Opposite direction: reduce, and possibly flip.
        closing_qty = min(abs(signed_qty), abs(self.qty))
        direction = 1.0 if self.qty > 0 else -1.0
        pnl = (price - self.avg_price) * closing_qty * direction
        self.realized_pnl += pnl
        self.qty += signed_qty

        if self.is_flat:
            self.qty = 0.0
            self.avg_price = 0.0
        elif (self.qty > 0) != (direction > 0):
            # Flipped through zero: the residual opens a fresh position at price.
            self.avg_price = price
        return pnl

    def add(self, qty: float, price: float) -> None:
        """Increase a long position (compatibility wrapper around :meth:`apply`)."""
        if qty <= 0.0:
            raise ValueError("qty must be positive")
        self.apply(qty, price)

    def reduce(self, qty: float, price: float) -> float:
        """Reduce a long position by ``qty`` (wrapper around :meth:`apply`).

        Raises:
            ValueError: If ``qty`` exceeds the long quantity held.
        """
        if qty <= 0.0:
            raise ValueError("qty must be positive")
        if qty > self.qty + 1e-9:
            raise ValueError(f"cannot sell {qty} of {self.symbol}; only {self.qty} held")
        return self.apply(-qty, price)

    def market_value(self, mark_price: float) -> float:
        """Return the signed marked value of the position at ``mark_price``."""
        return self.qty * mark_price

    def unrealized_pnl(self, mark_price: float) -> float:
        """Return open PnL versus the average entry at ``mark_price``.

        Works for both long and short positions (a short profits as the mark
        falls below the average entry).
        """
        if self.is_flat:
            return 0.0
        return (mark_price - self.avg_price) * self.qty
