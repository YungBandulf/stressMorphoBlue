"""Backtest framework — historical event validation per docs/BACKTEST.md."""

from morpho_stress.backtest.fixtures import (
    EventFixture,
    EventMeta,
    list_fixtures,
    load_event,
)
from morpho_stress.backtest.runner import (
    BacktestVerdict,
    CriterionResult,
    format_verdict,
    run_backtest,
)

__all__ = [
    "BacktestVerdict",
    "CriterionResult",
    "EventFixture",
    "EventMeta",
    "format_verdict",
    "list_fixtures",
    "load_event",
    "run_backtest",
]
