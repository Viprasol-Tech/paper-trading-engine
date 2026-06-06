"""Fee and slippage models for the Paper Trading Engine.

A :class:`FeeModel` turns a fill's quantity, price, and side into a commission
charged in cash. A :class:`SlippageModel` adjusts the *effective* execution price
away from the requested price to model the cost of crossing the spread or moving
the market. Both are small, composable strategies the engine applies on every
fill.

Part of Paper Trading Engine by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from paper_trading_engine.models import Side


class FeeModel(ABC):
    """Strategy that computes the commission charged on a single fill."""

    @abstractmethod
    def fee(self, qty: float, price: float, side: Side) -> float:
        """Return the (non-negative) commission for a fill of ``qty`` @ ``price``."""


class ZeroFee(FeeModel):
    """A commission-free model (the default for friction-free simulations)."""

    def fee(self, qty: float, price: float, side: Side) -> float:
        return 0.0


class PercentageFee(FeeModel):
    """A proportional fee charged on notional value (``qty * price``).

    Args:
        rate: Fraction of notional charged per fill (e.g. ``0.001`` = 10 bps).
            Must be in ``[0, 1)``.
    """

    def __init__(self, rate: float) -> None:
        if not 0.0 <= rate < 1.0:
            raise ValueError("rate must be in [0, 1)")
        self.rate = rate

    def fee(self, qty: float, price: float, side: Side) -> float:
        return qty * price * self.rate


class PerShareFee(FeeModel):
    """A flat fee charged per unit traded, with an optional per-order minimum.

    Models broker schedules like ``$0.005/share, $1.00 minimum``.

    Args:
        per_share: Fee charged for each unit; must be non-negative.
        minimum: Floor applied to the total per-order fee; must be non-negative.
    """

    def __init__(self, per_share: float, minimum: float = 0.0) -> None:
        if per_share < 0.0:
            raise ValueError("per_share must be non-negative")
        if minimum < 0.0:
            raise ValueError("minimum must be non-negative")
        self.per_share = per_share
        self.minimum = minimum

    def fee(self, qty: float, price: float, side: Side) -> float:
        return max(qty * self.per_share, self.minimum)


class FlatFee(FeeModel):
    """A fixed commission charged once per fill, regardless of size.

    Args:
        amount: Commission per fill; must be non-negative.
    """

    def __init__(self, amount: float) -> None:
        if amount < 0.0:
            raise ValueError("amount must be non-negative")
        self.amount = amount

    def fee(self, qty: float, price: float, side: Side) -> float:
        return self.amount


class SlippageModel(ABC):
    """Strategy that adjusts the requested price to an effective fill price."""

    @abstractmethod
    def fill_price(self, requested_price: float, side: Side) -> float:
        """Return the effective fill price for a market order at ``requested_price``."""


class NoSlippage(SlippageModel):
    """Fills exactly at the requested price (the default)."""

    def fill_price(self, requested_price: float, side: Side) -> float:
        return requested_price


class PercentageSlippage(SlippageModel):
    """Moves the price against the trader by a fixed fraction.

    Buys fill ``rate`` higher and sells fill ``rate`` lower, modelling adverse
    selection / crossing the spread.

    Args:
        rate: Fraction of price slipped against the order; must be in ``[0, 1)``.
    """

    def __init__(self, rate: float) -> None:
        if not 0.0 <= rate < 1.0:
            raise ValueError("rate must be in [0, 1)")
        self.rate = rate

    def fill_price(self, requested_price: float, side: Side) -> float:
        return requested_price * (1.0 + side.sign * self.rate)


class FixedSlippage(SlippageModel):
    """Moves the price against the trader by a fixed cash amount per unit.

    Args:
        ticks: Cash amount added to a buy / subtracted from a sell. The result
            is floored at a tiny positive epsilon so the price stays positive.
    """

    def __init__(self, ticks: float) -> None:
        if ticks < 0.0:
            raise ValueError("ticks must be non-negative")
        self.ticks = ticks

    def fill_price(self, requested_price: float, side: Side) -> float:
        return max(requested_price + side.sign * self.ticks, 1e-9)
