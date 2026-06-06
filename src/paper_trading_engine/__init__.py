"""Paper Trading Engine — simulated execution engine with positions and PnL by Viprasol Tech."""

from __future__ import annotations

from paper_trading_engine.engine import PaperEngine
from paper_trading_engine.fees import (
    FeeModel,
    FixedSlippage,
    FlatFee,
    NoSlippage,
    PercentageFee,
    PercentageSlippage,
    PerShareFee,
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
from paper_trading_engine.orderbook import OrderBook, RestingOrder, Trade
from paper_trading_engine.portfolio import (
    AccountReport,
    PnLReport,
    Portfolio,
    PositionReport,
)

__version__ = "0.2.0"
__author__ = "Viprasol Tech Private Limited"
__all__ = [
    "AccountReport",
    "FeeModel",
    "Fill",
    "FixedSlippage",
    "FlatFee",
    "NoSlippage",
    "Order",
    "OrderBook",
    "OrderStatus",
    "OrderType",
    "PaperEngine",
    "PerShareFee",
    "PercentageFee",
    "PercentageSlippage",
    "PnLReport",
    "Portfolio",
    "Position",
    "PositionReport",
    "RestingOrder",
    "Side",
    "SlippageModel",
    "Trade",
    "ZeroFee",
    "__version__",
]
