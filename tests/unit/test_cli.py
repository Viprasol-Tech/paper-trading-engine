"""Smoke tests for the Typer CLI subcommands."""

from __future__ import annotations

from typer.testing import CliRunner

from paper_trading_engine import __version__
from paper_trading_engine.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_demo_command_runs() -> None:
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "Open positions" in result.stdout
    assert "Realized PnL" in result.stdout


def test_demo_command_with_options() -> None:
    result = runner.invoke(
        app, ["demo", "--starting-cash", "50000", "--fee-rate", "0.0", "--slippage", "0.001"]
    )
    assert result.exit_code == 0
    assert "Final equity" in result.stdout


def test_report_command_runs() -> None:
    result = runner.invoke(app, ["report"])
    assert result.exit_code == 0
    assert "Accounts" in result.stdout
    assert "Total equity" in result.stdout


def test_book_command_runs() -> None:
    result = runner.invoke(app, ["book"])
    assert result.exit_code == 0
    assert "Best bid" in result.stdout
    assert "Trades" in result.stdout
