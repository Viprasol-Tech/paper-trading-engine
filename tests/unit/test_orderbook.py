"""Unit tests for the limit order book matching helper."""

from __future__ import annotations

import pytest

from paper_trading_engine.models import Side
from paper_trading_engine.orderbook import OrderBook


def test_resting_orders_report_best_prices_and_spread() -> None:
    ob = OrderBook("AAPL")
    ob.add_limit(Side.BUY, price=99.0, qty=5.0)
    ob.add_limit(Side.BUY, price=98.0, qty=5.0)
    ob.add_limit(Side.SELL, price=101.0, qty=5.0)
    ob.add_limit(Side.SELL, price=102.0, qty=5.0)

    assert ob.best_bid() == pytest.approx(99.0)
    assert ob.best_ask() == pytest.approx(101.0)
    assert ob.spread() == pytest.approx(2.0)
    assert ob.mid_price() == pytest.approx(100.0)


def test_empty_book_has_no_quotes() -> None:
    ob = OrderBook("X")
    assert ob.best_bid() is None
    assert ob.best_ask() is None
    assert ob.spread() is None
    assert ob.mid_price() is None
    assert ob.depth(Side.BUY) == 0.0


def test_marketable_limit_buy_partially_fills_then_rests() -> None:
    ob = OrderBook("AAPL")
    ob.add_limit(Side.SELL, price=101.0, qty=5.0, order_id="ask-1")
    trades = ob.add_limit(Side.BUY, price=101.0, qty=8.0, order_id="taker")

    # Fills 5 against ask-1, leaving 3 resting on the bid.
    assert len(trades) == 1
    assert trades[0].qty == pytest.approx(5.0)
    assert trades[0].price == pytest.approx(101.0)
    assert trades[0].maker_order_id == "ask-1"
    assert ob.best_bid() == pytest.approx(101.0)
    assert ob.depth(Side.BUY) == pytest.approx(3.0)
    assert ob.depth(Side.SELL) == 0.0


def test_price_priority_sweeps_best_levels_first() -> None:
    ob = OrderBook("AAPL")
    ob.add_limit(Side.SELL, price=102.0, qty=10.0, order_id="ask-2")
    ob.add_limit(Side.SELL, price=101.0, qty=5.0, order_id="ask-1")

    trades = ob.add_market(Side.BUY, qty=8.0, order_id="taker")
    # Best (cheapest) ask filled first.
    assert [t.price for t in trades] == [pytest.approx(101.0), pytest.approx(102.0)]
    assert [t.qty for t in trades] == [pytest.approx(5.0), pytest.approx(3.0)]
    assert ob.depth(Side.SELL) == pytest.approx(7.0)


def test_time_priority_fifo_at_same_price() -> None:
    ob = OrderBook("AAPL")
    ob.add_limit(Side.SELL, price=100.0, qty=5.0, order_id="first")
    ob.add_limit(Side.SELL, price=100.0, qty=5.0, order_id="second")

    trades = ob.add_market(Side.BUY, qty=6.0)
    assert trades[0].maker_order_id == "first"
    assert trades[0].qty == pytest.approx(5.0)
    assert trades[1].maker_order_id == "second"
    assert trades[1].qty == pytest.approx(1.0)


def test_non_marketable_limit_does_not_cross() -> None:
    ob = OrderBook("AAPL")
    ob.add_limit(Side.SELL, price=105.0, qty=5.0)
    trades = ob.add_limit(Side.BUY, price=100.0, qty=5.0)
    assert trades == []
    assert ob.best_bid() == pytest.approx(100.0)
    assert ob.best_ask() == pytest.approx(105.0)


def test_market_order_sweeps_and_discards_unfilled() -> None:
    ob = OrderBook("AAPL")
    ob.add_limit(Side.SELL, price=100.0, qty=3.0)
    trades = ob.add_market(Side.BUY, qty=10.0)
    assert sum(t.qty for t in trades) == pytest.approx(3.0)
    # No resting bid created from an unfilled market order.
    assert ob.best_bid() is None
    assert ob.depth(Side.SELL) == 0.0


def test_sell_hits_bids() -> None:
    ob = OrderBook("AAPL")
    ob.add_limit(Side.BUY, price=99.0, qty=4.0, order_id="bid-1")
    ob.add_limit(Side.BUY, price=98.0, qty=4.0, order_id="bid-2")
    trades = ob.add_limit(Side.SELL, price=98.0, qty=6.0, order_id="seller")
    assert trades[0].maker_order_id == "bid-1"
    assert trades[1].maker_order_id == "bid-2"
    assert sum(t.qty for t in trades) == pytest.approx(6.0)
    assert ob.depth(Side.BUY) == pytest.approx(2.0)


def test_cancel_removes_resting_orders() -> None:
    ob = OrderBook("AAPL")
    ob.add_limit(Side.BUY, price=99.0, qty=5.0, order_id="bid-1")
    assert ob.cancel("bid-1") == 1
    assert ob.best_bid() is None
    assert ob.cancel("nope") == 0


def test_add_limit_rejects_bad_inputs() -> None:
    ob = OrderBook("AAPL")
    with pytest.raises(ValueError, match="price"):
        ob.add_limit(Side.BUY, price=0.0, qty=1.0)
    with pytest.raises(ValueError, match="qty"):
        ob.add_limit(Side.BUY, price=1.0, qty=0.0)
    with pytest.raises(ValueError, match="qty"):
        ob.add_market(Side.BUY, qty=-1.0)
