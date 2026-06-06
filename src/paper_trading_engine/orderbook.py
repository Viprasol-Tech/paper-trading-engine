"""A minimal price-time-priority limit order book matching helper.

:class:`OrderBook` keeps resting bids and asks for a single symbol and matches
incoming orders against the opposite side, producing :class:`Trade` records with
partial-fill support. Matching is deterministic: best price first, then earliest
arrival (FIFO) at the same price.

This is a self-contained matching utility; it does not touch cash or positions.
Feed the resulting trades into :class:`~paper_trading_engine.engine.PaperEngine`
if you want them settled.

Part of Paper Trading Engine by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

import itertools

from pydantic import BaseModel, Field

from paper_trading_engine.models import Side

_seq = itertools.count(1)


class RestingOrder(BaseModel):
    """A resting limit order on one side of the book."""

    seq: int = Field(default_factory=lambda: next(_seq))
    side: Side
    price: float = Field(gt=0.0)
    qty: float = Field(gt=0.0)
    order_id: str | None = None


class Trade(BaseModel):
    """An executed match between an incoming order and a resting order."""

    price: float
    qty: float
    taker_side: Side
    maker_order_id: str | None = None
    taker_order_id: str | None = None


class OrderBook:
    """A single-symbol limit order book with price-time priority matching.

    Args:
        symbol: Instrument identifier the book represents.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._bids: list[RestingOrder] = []
        self._asks: list[RestingOrder] = []

    # -- introspection -------------------------------------------------------

    @property
    def bids(self) -> list[RestingOrder]:
        """Resting buy orders, sorted best (highest price, earliest) first."""
        return sorted(self._bids, key=lambda o: (-o.price, o.seq))

    @property
    def asks(self) -> list[RestingOrder]:
        """Resting sell orders, sorted best (lowest price, earliest) first."""
        return sorted(self._asks, key=lambda o: (o.price, o.seq))

    def best_bid(self) -> float | None:
        """Highest resting bid price, or ``None`` if there are no bids."""
        bids = self.bids
        return bids[0].price if bids else None

    def best_ask(self) -> float | None:
        """Lowest resting ask price, or ``None`` if there are no asks."""
        asks = self.asks
        return asks[0].price if asks else None

    def spread(self) -> float | None:
        """Best ask minus best bid, or ``None`` if either side is empty."""
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return ask - bid

    def mid_price(self) -> float | None:
        """Midpoint of best bid and ask, or ``None`` if either side is empty."""
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2.0

    def depth(self, side: Side) -> float:
        """Total resting quantity on ``side``."""
        book = self._bids if side is Side.BUY else self._asks
        return sum(o.qty for o in book)

    # -- mutation ------------------------------------------------------------

    def add_limit(
        self, side: Side, price: float, qty: float, order_id: str | None = None
    ) -> list[Trade]:
        """Add a limit order, matching marketable quantity and resting the rest.

        Args:
            side: :class:`Side.BUY` or :class:`Side.SELL`.
            price: Limit price; must be positive.
            qty: Quantity; must be positive.
            order_id: Optional identifier echoed back on resulting trades.

        Returns:
            The trades generated as the order crosses the book (possibly empty).
        """
        if price <= 0.0:
            raise ValueError("price must be positive")
        if qty <= 0.0:
            raise ValueError("qty must be positive")

        trades = self._match(side, qty, limit_price=price, taker_order_id=order_id)
        filled = sum(t.qty for t in trades)
        remaining = qty - filled
        if remaining > 1e-9:
            book = self._bids if side is Side.BUY else self._asks
            book.append(RestingOrder(side=side, price=price, qty=remaining, order_id=order_id))
        return trades

    def add_market(self, side: Side, qty: float, order_id: str | None = None) -> list[Trade]:
        """Add a market order that sweeps the opposite side until filled.

        Unfilled quantity is discarded (the book has no more liquidity); it does
        not rest.

        Args:
            side: :class:`Side.BUY` or :class:`Side.SELL`.
            qty: Quantity; must be positive.
            order_id: Optional identifier echoed back on resulting trades.

        Returns:
            The trades generated while sweeping (possibly empty).
        """
        if qty <= 0.0:
            raise ValueError("qty must be positive")
        return self._match(side, qty, limit_price=None, taker_order_id=order_id)

    def cancel(self, order_id: str) -> int:
        """Remove all resting orders carrying ``order_id``.

        Returns:
            The number of resting orders removed.
        """
        before = len(self._bids) + len(self._asks)
        self._bids = [o for o in self._bids if o.order_id != order_id]
        self._asks = [o for o in self._asks if o.order_id != order_id]
        return before - (len(self._bids) + len(self._asks))

    # -- internals -----------------------------------------------------------

    def _match(
        self,
        side: Side,
        qty: float,
        *,
        limit_price: float | None,
        taker_order_id: str | None,
    ) -> list[Trade]:
        """Cross ``qty`` of ``side`` against the resting opposite side."""
        trades: list[Trade] = []
        remaining = qty
        # Buyers lift asks; sellers hit bids.
        resting = self.asks if side is Side.BUY else self.bids
        for maker in resting:
            if remaining <= 1e-9:
                break
            if limit_price is not None:
                crosses = (
                    maker.price <= limit_price + 1e-9
                    if side is Side.BUY
                    else maker.price >= limit_price - 1e-9
                )
                if not crosses:
                    break  # price-sorted: nothing further can cross either
            traded = min(remaining, maker.qty)
            trades.append(
                Trade(
                    price=maker.price,
                    qty=traded,
                    taker_side=side,
                    maker_order_id=maker.order_id,
                    taker_order_id=taker_order_id,
                )
            )
            maker.qty -= traded
            remaining -= traded

        # Drop fully consumed resting orders.
        self._asks = [o for o in self._asks if o.qty > 1e-9]
        self._bids = [o for o in self._bids if o.qty > 1e-9]
        return trades
