"""Unit tests for multi-account portfolios and PnL reporting."""

from __future__ import annotations

import pytest

from paper_trading_engine.engine import PaperEngine
from paper_trading_engine.models import Side
from paper_trading_engine.portfolio import Portfolio


def test_open_account_and_lookup() -> None:
    pf = Portfolio()
    eng = pf.open_account("alpha", starting_cash=5_000.0)
    assert isinstance(eng, PaperEngine)
    assert pf.account("alpha") is eng
    assert "alpha" in pf
    assert pf.names() == ["alpha"]
    assert len(pf) == 1


def test_duplicate_account_rejected() -> None:
    pf = Portfolio()
    pf.open_account("alpha")
    with pytest.raises(ValueError, match="already exists"):
        pf.open_account("alpha")
    with pytest.raises(ValueError, match="already exists"):
        pf.add_account("alpha", PaperEngine())


def test_unknown_account_raises() -> None:
    pf = Portfolio()
    with pytest.raises(KeyError, match="beta"):
        pf.account("beta")


def test_open_account_forwards_kwargs() -> None:
    pf = Portfolio()
    eng = pf.open_account("short-book", starting_cash=10_000.0, allow_short=True, fee_rate=0.002)
    assert eng.allow_short is True
    assert eng.fee_rate == pytest.approx(0.002)


def test_total_equity_sums_accounts() -> None:
    pf = Portfolio()
    a = pf.open_account("a", starting_cash=10_000.0)
    b = pf.open_account("b", starting_cash=20_000.0)
    a.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    b.submit_market_order("MSFT", Side.BUY, qty=10.0, price=200.0)
    marks = {"AAPL": 110.0, "MSFT": 200.0}
    # a: 9_000 cash + 1_100 = 10_100 ; b: 18_000 + 2_000 = 20_000.
    assert pf.total_equity(marks) == pytest.approx(30_100.0)


def test_report_rolls_up_realized_and_unrealized() -> None:
    pf = Portfolio()
    mom = pf.open_account("momentum", starting_cash=20_000.0, fee_rate=0.0)
    rev = pf.open_account("reversion", starting_cash=15_000.0, allow_short=True)

    mom.submit_market_order("AAPL", Side.BUY, qty=50.0, price=100.0)
    mom.submit_market_order("AAPL", Side.SELL, qty=20.0, price=115.0)  # realizes (115-100)*20=300
    rev.submit_market_order("TSLA", Side.SELL, qty=10.0, price=250.0)  # short

    marks = {"AAPL": 120.0, "TSLA": 240.0}
    rep = pf.report(marks)

    assert len(rep.accounts) == 2
    assert len(rep.positions) == 2

    mom_report = next(a for a in rep.accounts if a.name == "momentum")
    assert mom_report.realized_pnl == pytest.approx(300.0)
    # 30 shares left @ avg 100, marked 120 -> 600 unrealized.
    assert mom_report.unrealized_pnl == pytest.approx(600.0)

    rev_report = next(a for a in rep.accounts if a.name == "reversion")
    # Short 10 @ 250, marked 240 -> +100 unrealized.
    assert rev_report.unrealized_pnl == pytest.approx(100.0)

    assert rep.total_realized_pnl == pytest.approx(300.0)
    assert rep.total_unrealized_pnl == pytest.approx(700.0)


def test_report_return_pct() -> None:
    pf = Portfolio()
    eng = pf.open_account("solo", starting_cash=10_000.0)
    eng.submit_market_order("AAPL", Side.BUY, qty=10.0, price=100.0)
    marks = {"AAPL": 200.0}  # position now worth 2_000, cash 9_000 -> equity 11_000
    rep = pf.report(marks)
    solo = rep.accounts[0]
    assert solo.equity == pytest.approx(11_000.0)
    assert solo.return_pct == pytest.approx(10.0)
    assert rep.total_return_pct == pytest.approx(10.0)


def test_position_report_detail() -> None:
    pf = Portfolio()
    eng = pf.open_account("solo", starting_cash=10_000.0)
    eng.submit_market_order("AAPL", Side.BUY, qty=5.0, price=100.0)
    rep = pf.report({"AAPL": 110.0})
    pos = rep.positions[0]
    assert pos.account == "solo"
    assert pos.symbol == "AAPL"
    assert pos.qty == pytest.approx(5.0)
    assert pos.market_value == pytest.approx(550.0)
    assert pos.unrealized_pnl == pytest.approx(50.0)
