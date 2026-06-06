"""Simulated paper-trading execution engine.

:class:`PaperEngine` fills market and limit orders against caller-supplied
prices, debits/credits cash, applies pluggable fee and slippage models,
maintains per-symbol :class:`~paper_trading_engine.models.Position` records with
volume-weighted average entry (long *or* short), and tracks realized and
unrealized PnL. Equity is reported by marking open positions to a price map.

Part of Paper Trading Engine by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from collections.abc import Mapping

from paper_trading_engine.fees import (
    FeeModel,
    NoSlippage,
    PercentageFee,
    SlippageModel,
    ZeroFee,
)
from paper_trading_engine.models import (
    Fill,
    Order,
    OrderStatus,
    OrderType,
    Position,
    Side,
)


class PaperEngine:
    """A cash-settled simulated execution engine for market and limit orders.

    Args:
        starting_cash: Initial cash balance; must be non-negative.
        fee_rate: Backwards-compatible proportional fee on notional (e.g.
            ``0.001`` for 10 bps). Ignored if ``fee_model`` is given. Must be in
            ``[0, 1)``.
        fee_model: Pluggable :class:`~paper_trading_engine.fees.FeeModel`. When
            omitted, a :class:`PercentageFee` built from ``fee_rate`` is used.
        slippage_model: Pluggable
            :class:`~paper_trading_engine.fees.SlippageModel` applied to market
            orders. Defaults to no slippage.
        allow_short: When ``True``, sells may open or extend a short position;
            when ``False`` (default) selling more than is held is rejected.
    """

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        fee_rate: float = 0.0,
        *,
        fee_model: FeeModel | None = None,
        slippage_model: SlippageModel | None = None,
        allow_short: bool = False,
    ) -> None:
        if starting_cash < 0.0:
            raise ValueError("starting_cash must be non-negative")
        if not 0.0 <= fee_rate < 1.0:
            raise ValueError("fee_rate must be in [0, 1)")
        self.starting_cash: float = starting_cash
        self.cash: float = starting_cash
        self.fee_rate: float = fee_rate
        self.fee_model: FeeModel = fee_model or (
            PercentageFee(fee_rate) if fee_rate > 0.0 else ZeroFee()
        )
        self.slippage_model: SlippageModel = slippage_model or NoSlippage()
        self.allow_short: bool = allow_short
        self._positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self.orders: list[Order] = []

    # -- order entry ---------------------------------------------------------

    def submit_market_order(
        self, symbol: str, side: Side, qty: float, price: float, order_id: str | None = None
    ) -> Fill:
        """Fill a market order at ``price`` (after slippage) and settle it.

        A buy debits ``qty * fill_price + fee`` from cash and grows the position;
        a sell credits ``qty * fill_price - fee`` to cash, reduces (or opens a
        short, if enabled) the position, and realizes PnL.

        Args:
            symbol: Instrument identifier (e.g. ``"AAPL"``).
            side: :class:`Side.BUY` or :class:`Side.SELL`.
            qty: Quantity to trade; must be positive.
            price: Reference execution price; must be positive.
            order_id: Optional identifier stamped onto the resulting fill.

        Returns:
            The recorded :class:`Fill`.

        Raises:
            ValueError: If ``qty``/``price`` are non-positive, a buy cannot be
                afforded, or a sell exceeds held quantity (when shorting is off).
        """
        if qty <= 0.0:
            raise ValueError("qty must be positive")
        if price <= 0.0:
            raise ValueError("price must be positive")
        fill_price = self.slippage_model.fill_price(price, side)
        return self._execute(symbol, side, qty, fill_price, order_id)

    def submit_limit_order(
        self, symbol: str, side: Side, qty: float, limit_price: float, market_price: float
    ) -> Order:
        """Submit a limit order and fill it if the market price is marketable.

        A buy fills when ``market_price <= limit_price``; a sell fills when
        ``market_price >= limit_price``. The fill executes at the better of the
        two prices (the limit for the taker), mirroring a price-improved cross.
        Non-marketable orders rest with status :class:`OrderStatus.NEW`.

        Args:
            symbol: Instrument identifier.
            side: :class:`Side.BUY` or :class:`Side.SELL`.
            qty: Quantity; must be positive.
            limit_price: Worst acceptable price; must be positive.
            market_price: Current reference price used to decide marketability.

        Returns:
            The :class:`Order`, marked ``FILLED`` or left ``NEW`` (resting).
        """
        if qty <= 0.0:
            raise ValueError("qty must be positive")
        if limit_price <= 0.0:
            raise ValueError("limit_price must be positive")
        if market_price <= 0.0:
            raise ValueError("market_price must be positive")

        order = Order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
        )
        self.orders.append(order)
        if order.accepts_price(market_price):
            # Buyers never pay above the limit; sellers never accept below it.
            if side is Side.BUY:
                exec_price = min(market_price, limit_price)
            else:
                exec_price = max(market_price, limit_price)
            try:
                self._execute(symbol, side, qty, exec_price, order.id)
            except ValueError:
                order.status = OrderStatus.REJECTED
                raise
            order.record_fill(qty)
        return order

    def fill_resting_order(self, order: Order, qty: float, price: float) -> Fill:
        """Apply a partial (or full) fill to a resting order at ``price``.

        Use this to drive a previously-rested limit order toward completion as
        liquidity arrives, e.g. matching against an
        :class:`~paper_trading_engine.orderbook.OrderBook`.

        Args:
            order: An open order previously returned by :meth:`submit_limit_order`.
            qty: Quantity to fill now; must be positive and within ``remaining``.
            price: Execution price; must satisfy the order's limit and be positive.

        Returns:
            The recorded :class:`Fill`.

        Raises:
            ValueError: If the order is not open, ``qty`` exceeds remaining, or
                ``price`` violates the limit.
        """
        if not order.is_open:
            raise ValueError(f"order {order.id} is not open (status={order.status.value})")
        if not order.accepts_price(price):
            raise ValueError(f"price {price} violates limit {order.limit_price} for {order.side}")
        fill = self._execute(order.symbol, order.side, qty, price, order.id)
        order.record_fill(qty)
        return fill

    def cancel_order(self, order: Order) -> bool:
        """Cancel an open order. Returns ``True`` if it was open, else ``False``."""
        if order.is_open:
            order.status = OrderStatus.CANCELLED
            return True
        return False

    def open_orders(self) -> list[Order]:
        """Return all orders still open (resting or partially filled)."""
        return [o for o in self.orders if o.is_open]

    # -- settlement ----------------------------------------------------------

    def _execute(
        self, symbol: str, side: Side, qty: float, price: float, order_id: str | None
    ) -> Fill:
        """Settle a fill of ``qty`` @ ``price`` against cash and positions."""
        if qty <= 0.0:
            raise ValueError("qty must be positive")
        if price <= 0.0:
            raise ValueError("price must be positive")

        notional = qty * price
        fee = self.fee_model.fee(qty, price, side)
        position = self._positions.setdefault(symbol, Position(symbol=symbol))

        if side is Side.BUY:
            total_cost = notional + fee
            if total_cost > self.cash + 1e-9:
                raise ValueError(
                    f"insufficient cash for buy: need {total_cost:.2f}, have {self.cash:.2f}"
                )
            position.apply(qty, price)
            self.cash -= total_cost
        else:
            if not self.allow_short and qty > position.qty + 1e-9:
                raise ValueError(f"cannot sell {qty} of {symbol}; only {position.qty} held")
            position.apply(-qty, price)
            self.cash += notional - fee

        fill = Fill(symbol=symbol, side=side, qty=qty, price=price, fee=fee, order_id=order_id)
        self.fills.append(fill)
        return fill

    # -- reporting -----------------------------------------------------------

    def position(self, symbol: str) -> Position:
        """Return the position for ``symbol`` (a flat position if untouched)."""
        return self._positions.get(symbol, Position(symbol=symbol))

    def positions(self) -> dict[str, Position]:
        """Return a mapping of all open (non-flat) positions by symbol."""
        return {sym: pos for sym, pos in self._positions.items() if not pos.is_flat}

    def realized_pnl(self) -> float:
        """Return total realized PnL across all symbols (sells/closes, pre-fee)."""
        return sum(pos.realized_pnl for pos in self._positions.values())

    def unrealized_pnl(self, mark_prices: Mapping[str, float]) -> float:
        """Return total open PnL across all positions at ``mark_prices``."""
        total = 0.0
        for sym, pos in self._positions.items():
            if pos.is_flat:
                continue
            if sym not in mark_prices:
                raise KeyError(f"no mark price supplied for open position {sym!r}")
            total += pos.unrealized_pnl(mark_prices[sym])
        return total

    def fees_paid(self) -> float:
        """Return the total fees charged across all fills."""
        return sum(fill.fee for fill in self.fills)

    def positions_value(self, mark_prices: Mapping[str, float]) -> float:
        """Return the signed marked value of all open positions.

        Args:
            mark_prices: Current price per symbol. Symbols with a non-flat
                position but no mark price raise :class:`KeyError`.
        """
        total = 0.0
        for sym, pos in self._positions.items():
            if pos.is_flat:
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

    def total_pnl(self, mark_prices: Mapping[str, float]) -> float:
        """Return realized + unrealized PnL net of fees paid."""
        return self.realized_pnl() + self.unrealized_pnl(mark_prices) - self.fees_paid()
