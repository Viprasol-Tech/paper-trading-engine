"""Unit tests for fee and slippage models."""

from __future__ import annotations

import pytest

from paper_trading_engine.fees import (
    FixedSlippage,
    FlatFee,
    NoSlippage,
    PercentageFee,
    PercentageSlippage,
    PerShareFee,
    ZeroFee,
)
from paper_trading_engine.models import Side


def test_zero_fee_is_free() -> None:
    assert ZeroFee().fee(100.0, 50.0, Side.BUY) == 0.0


def test_percentage_fee_on_notional() -> None:
    model = PercentageFee(0.001)
    # 10 * 100 * 0.001 = 1.0
    assert model.fee(10.0, 100.0, Side.BUY) == pytest.approx(1.0)
    assert model.fee(10.0, 100.0, Side.SELL) == pytest.approx(1.0)


def test_percentage_fee_rejects_bad_rate() -> None:
    with pytest.raises(ValueError, match="rate"):
        PercentageFee(1.0)
    with pytest.raises(ValueError, match="rate"):
        PercentageFee(-0.1)


def test_per_share_fee_with_minimum() -> None:
    model = PerShareFee(per_share=0.005, minimum=1.0)
    # 50 * 0.005 = 0.25, floored to the 1.0 minimum.
    assert model.fee(50.0, 10.0, Side.BUY) == pytest.approx(1.0)
    # 400 * 0.005 = 2.0, above the minimum.
    assert model.fee(400.0, 10.0, Side.SELL) == pytest.approx(2.0)


def test_per_share_fee_rejects_negatives() -> None:
    with pytest.raises(ValueError, match="per_share"):
        PerShareFee(-0.1)
    with pytest.raises(ValueError, match="minimum"):
        PerShareFee(0.01, minimum=-1.0)


def test_flat_fee_is_constant() -> None:
    model = FlatFee(2.5)
    assert model.fee(1.0, 10.0, Side.BUY) == pytest.approx(2.5)
    assert model.fee(1000.0, 99.0, Side.SELL) == pytest.approx(2.5)


def test_flat_fee_rejects_negative() -> None:
    with pytest.raises(ValueError, match="amount"):
        FlatFee(-1.0)


def test_no_slippage_passthrough() -> None:
    model = NoSlippage()
    assert model.fill_price(100.0, Side.BUY) == 100.0
    assert model.fill_price(100.0, Side.SELL) == 100.0


def test_percentage_slippage_moves_against_trader() -> None:
    model = PercentageSlippage(0.01)
    # Buys pay 1% more, sells receive 1% less.
    assert model.fill_price(100.0, Side.BUY) == pytest.approx(101.0)
    assert model.fill_price(100.0, Side.SELL) == pytest.approx(99.0)


def test_percentage_slippage_rejects_bad_rate() -> None:
    with pytest.raises(ValueError, match="rate"):
        PercentageSlippage(1.5)


def test_fixed_slippage_moves_against_trader() -> None:
    model = FixedSlippage(0.5)
    assert model.fill_price(100.0, Side.BUY) == pytest.approx(100.5)
    assert model.fill_price(100.0, Side.SELL) == pytest.approx(99.5)


def test_fixed_slippage_keeps_price_positive() -> None:
    model = FixedSlippage(1000.0)
    assert model.fill_price(1.0, Side.SELL) > 0.0


def test_fixed_slippage_rejects_negative() -> None:
    with pytest.raises(ValueError, match="ticks"):
        FixedSlippage(-1.0)
