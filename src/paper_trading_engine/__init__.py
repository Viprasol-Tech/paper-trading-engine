"""Paper Trading Engine — simulated execution engine with positions and PnL by Viprasol Tech."""

from __future__ import annotations

from paper_trading_engine.engine import PaperEngine
from paper_trading_engine.models import Fill, Position, Side

__version__ = "0.1.0"
__author__ = "Viprasol Tech Private Limited"
__all__ = ["Fill", "PaperEngine", "Position", "Side", "__version__"]
