"""Unit tests for the Paper Trading Engine."""

from __future__ import annotations

import math

import pytest

from paper_trading_engine.engine import PaperEngine
from paper_trading_engine.models import Position, Side


def test_buy_then_sell_realizes_correct_pnl() -> None:
    engine = PaperEngine(starting_cash=10_000.0, fee_rate=0.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    engine.submit_market_order("AAPL", Side.SELL, qty=10.0, price=120.0)

    # Bought 10 @ 100, sold 10 @ 120 -> realized PnL = (120 - 100) * 10 = 200.
    assert engine.realized_pnl() == pytest.approx(200.0)
    assert engine.position("AAPL").qty == pytest.approx(0.0)
    # Cash: 10_000 - 1_000 (buy) + 1_200 (sell) = 10_200.
    assert engine.cash == pytest.approx(10_200.0)


def test_volume_weighted_average_entry() -> None:
    engine = PaperEngine(starting_cash=10_000.0, fee_rate=0.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=110.0)

    pos = engine.position("AAPL")
    assert pos.qty == pytest.approx(20.0)
    # VWAP = (10*100 + 10*110) / 20 = 105.
    assert pos.avg_price == pytest.approx(105.0)

    # Selling 5 @ 120 realizes (120 - 105) * 5 = 75.
    engine.submit_market_order("AAPL", Side.SELL, qty=5.0, price=120.0)
    assert engine.realized_pnl() == pytest.approx(75.0)
    assert engine.position("AAPL").qty == pytest.approx(15.0)
    assert engine.position("AAPL").avg_price == pytest.approx(105.0)


def test_equity_equals_cash_plus_marked_positions() -> None:
    engine = PaperEngine(starting_cash=10_000.0, fee_rate=0.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    # Cash left = 9_000; mark AAPL at 130 -> positions value = 1_300.
    marks = {"AAPL": 130.0}
    assert engine.positions_value(marks) == pytest.approx(1_300.0)
    assert engine.equity(marks) == pytest.approx(engine.cash + 1_300.0)
    assert engine.equity(marks) == pytest.approx(10_300.0)


def test_fees_reduce_cash() -> None:
    engine = PaperEngine(starting_cash=10_000.0, fee_rate=0.01)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    # Notional 1_000, fee 1% = 10 -> cash = 10_000 - 1_000 - 10 = 8_990.
    assert engine.cash == pytest.approx(8_990.0)
    assert engine.fees_paid() == pytest.approx(10.0)

    no_fee = PaperEngine(starting_cash=10_000.0, fee_rate=0.0)
    no_fee.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    assert engine.cash < no_fee.cash


def test_sell_proceeds_net_of_fees() -> None:
    engine = PaperEngine(starting_cash=10_000.0, fee_rate=0.005)
    engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    cash_after_buy = engine.cash
    engine.submit_market_order("AAPL", Side.SELL, qty=10.0, price=100.0)
    # Sell notional 1_000, fee 0.5% = 5 -> credit 995.
    assert engine.cash == pytest.approx(cash_after_buy + 995.0)


def test_oversell_raises() -> None:
    engine = PaperEngine(starting_cash=10_000.0, fee_rate=0.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=5.0, price=100.0)
    with pytest.raises(ValueError, match="cannot sell"):
        engine.submit_market_order("AAPL", Side.SELL, qty=10.0, price=100.0)


def test_insufficient_cash_raises() -> None:
    engine = PaperEngine(starting_cash=500.0, fee_rate=0.0)
    with pytest.raises(ValueError, match="insufficient cash"):
        engine.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)


def test_invalid_order_inputs() -> None:
    engine = PaperEngine()
    with pytest.raises(ValueError, match="qty must be positive"):
        engine.submit_market_order("AAPL", Side.BUY, qty=0.0, price=100.0)
    with pytest.raises(ValueError, match="price must be positive"):
        engine.submit_market_order("AAPL", Side.BUY, qty=1.0, price=0.0)


def test_invalid_engine_construction() -> None:
    with pytest.raises(ValueError, match="starting_cash"):
        PaperEngine(starting_cash=-1.0)
    with pytest.raises(ValueError, match="fee_rate"):
        PaperEngine(fee_rate=1.0)


def test_equity_missing_mark_price_raises() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=1.0, price=100.0)
    with pytest.raises(KeyError, match="AAPL"):
        engine.equity({})


def test_flat_position_after_full_exit() -> None:
    engine = PaperEngine(starting_cash=10_000.0)
    engine.submit_market_order("AAPL", Side.BUY, qty=3.0, price=50.0)
    engine.submit_market_order("AAPL", Side.SELL, qty=3.0, price=60.0)
    assert engine.positions() == {}
    assert engine.position("AAPL").avg_price == 0.0


def test_side_sign() -> None:
    assert Side.BUY.sign == 1
    assert Side.SELL.sign == -1


def test_position_model_round_trip() -> None:
    pos = Position(symbol="X")
    pos.add(10.0, 10.0)
    pos.add(10.0, 20.0)
    assert math.isclose(pos.avg_price, 15.0)
    realized = pos.reduce(5.0, 25.0)
    assert math.isclose(realized, (25.0 - 15.0) * 5.0)
