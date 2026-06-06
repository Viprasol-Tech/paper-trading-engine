"""Unit tests for advanced engine features: limits, partial fills, shorts, slippage."""

from __future__ import annotations

import pytest

from paper_trading_engine.engine import PaperEngine
from paper_trading_engine.fees import FlatFee, PercentageSlippage
from paper_trading_engine.models import OrderStatus, OrderType, Position, Side


def test_marketable_limit_buy_fills_at_limit_or_better() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    order = engine.submit_limit_order(
        "AAPL", Side.BUY, qty=10.0, limit_price=105.0, market_price=100.0
    )
    assert order.status is OrderStatus.FILLED
    assert order.order_type is OrderType.LIMIT
    # Buyer gets price improvement to the market price (100), not the limit (105).
    assert engine.position("AAPL").avg_price == pytest.approx(100.0)
    assert engine.cash == pytest.approx(9_000.0)


def test_non_marketable_limit_rests() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    order = engine.submit_limit_order(
        "AAPL", Side.BUY, qty=10.0, limit_price=95.0, market_price=100.0
    )
    assert order.status is OrderStatus.NEW
    assert order.remaining == pytest.approx(10.0)
    assert engine.cash == pytest.approx(10_000.0)
    assert order in engine.open_orders()


def test_resting_order_partial_fills() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    order = engine.submit_limit_order(
        "AAPL", Side.BUY, qty=10.0, limit_price=95.0, market_price=100.0
    )
    engine.fill_resting_order(order, qty=4.0, price=95.0)
    assert order.status is OrderStatus.PARTIALLY_FILLED
    assert order.filled_qty == pytest.approx(4.0)
    assert order.remaining == pytest.approx(6.0)

    engine.fill_resting_order(order, qty=6.0, price=94.0)
    assert order.status is OrderStatus.FILLED
    assert order.remaining == pytest.approx(0.0)
    # 4 @ 95 + 6 @ 94 = 944 over 10 shares -> avg 94.4
    assert engine.position("AAPL").avg_price == pytest.approx(94.4)


def test_fill_resting_order_rejects_limit_violation() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    order = engine.submit_limit_order(
        "AAPL", Side.BUY, qty=10.0, limit_price=95.0, market_price=100.0
    )
    with pytest.raises(ValueError, match="violates limit"):
        engine.fill_resting_order(order, qty=1.0, price=96.0)


def test_fill_closed_order_rejected() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    order = engine.submit_limit_order(
        "AAPL", Side.BUY, qty=1.0, limit_price=105.0, market_price=100.0
    )
    assert order.status is OrderStatus.FILLED
    with pytest.raises(ValueError, match="not open"):
        engine.fill_resting_order(order, qty=1.0, price=100.0)


def test_cancel_order() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    order = engine.submit_limit_order(
        "AAPL", Side.BUY, qty=10.0, limit_price=95.0, market_price=100.0
    )
    assert engine.cancel_order(order) is True
    assert order.status is OrderStatus.CANCELLED
    assert engine.open_orders() == []
    # Cancelling again is a no-op.
    assert engine.cancel_order(order) is False


def test_short_selling_when_enabled() -> None:
    engine = PaperEngine(starting_cash=10_000.0, allow_short=True)
    engine.submit_market_order("TSLA", Side.SELL, qty=10.0, price=250.0)
    pos = engine.position("TSLA")
    assert pos.is_short
    assert pos.qty == pytest.approx(-10.0)
    assert pos.avg_price == pytest.approx(250.0)
    # Cash credited the sale proceeds.
    assert engine.cash == pytest.approx(12_500.0)


def test_short_unrealized_pnl_profits_as_price_falls() -> None:
    engine = PaperEngine(starting_cash=10_000.0, allow_short=True)
    engine.submit_market_order("TSLA", Side.SELL, qty=10.0, price=250.0)
    # Mark drops to 240 -> short gains (250-240)*10 = 100.
    assert engine.unrealized_pnl({"TSLA": 240.0}) == pytest.approx(100.0)
    # Mark rises to 260 -> short loses 100.
    assert engine.unrealized_pnl({"TSLA": 260.0}) == pytest.approx(-100.0)


def test_short_cover_realizes_pnl() -> None:
    engine = PaperEngine(starting_cash=10_000.0, allow_short=True)
    engine.submit_market_order("TSLA", Side.SELL, qty=10.0, price=250.0)
    engine.submit_market_order("TSLA", Side.BUY, qty=10.0, price=240.0)
    # Covered cheaper -> realized profit (250-240)*10 = 100.
    assert engine.realized_pnl() == pytest.approx(100.0)
    assert engine.position("TSLA").is_flat


def test_short_disabled_by_default() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    with pytest.raises(ValueError, match="cannot sell"):
        engine.submit_market_order("TSLA", Side.SELL, qty=10.0, price=250.0)


def test_position_flip_long_to_short() -> None:
    engine = PaperEngine(starting_cash=100_000.0, allow_short=True)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    # Sell 15: closes 10 long (realize (110-100)*10=100) and opens 5 short @ 110.
    engine.submit_market_order("AAPL", Side.SELL, qty=15.0, price=110.0)
    pos = engine.position("AAPL")
    assert pos.qty == pytest.approx(-5.0)
    assert pos.avg_price == pytest.approx(110.0)
    assert pos.realized_pnl == pytest.approx(100.0)


def test_slippage_moves_market_fill_price() -> None:
    engine = PaperEngine(starting_cash=10_000.0, slippage_model=PercentageSlippage(0.01))
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    # Buy slips up 1% -> fills at 101.
    assert engine.position("AAPL").avg_price == pytest.approx(101.0)


def test_pluggable_flat_fee_model() -> None:
    engine = PaperEngine(starting_cash=10_000.0, fee_model=FlatFee(5.0))
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    assert engine.fees_paid() == pytest.approx(5.0)
    assert engine.cash == pytest.approx(10_000.0 - 1_000.0 - 5.0)


def test_total_pnl_combines_realized_unrealized_fees() -> None:
    engine = PaperEngine(starting_cash=10_000.0, fee_model=FlatFee(1.0))
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    engine.submit_market_order("AAPL", Side.SELL, qty=5.0, price=110.0)  # realize +50
    marks = {"AAPL": 120.0}
    # realized 50 ; unrealized (120-100)*15 = 300 ; fees 3 -> total 347.
    assert engine.total_pnl(marks) == pytest.approx(50.0 + 300.0 - 3.0)


def test_orders_recorded_on_limit_submission() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    engine.submit_limit_order("AAPL", Side.BUY, qty=1.0, limit_price=95.0, market_price=100.0)
    assert len(engine.orders) == 1


def test_position_unrealized_pnl_flat_is_zero() -> None:
    pos = Position(symbol="X")
    assert pos.unrealized_pnl(100.0) == 0.0


def test_fill_carries_order_id() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    order = engine.submit_limit_order(
        "AAPL", Side.BUY, qty=1.0, limit_price=105.0, market_price=100.0
    )
    assert engine.fills[-1].order_id == order.id
