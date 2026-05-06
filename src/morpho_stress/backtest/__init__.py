"""Backtest framework — historical event validation per docs/BACKTEST.md."""

from morpho_stress.backtest.fixtures import (
    EventFixture,
    EventMeta,
    list_fixtures,
    load_event,
)
from morpho_stress.backtest.liquidity_metrics import (
    calibrated_outflow_alpha,
    hqla_v03,
    lcr_onchain_v03,
    position_recovery_value,
)
from morpho_stress.backtest.forward_looking import (
    MarketProfile,
    MarketRiskAssessment,
    assess_all_markets,
    assess_market,
    current_markets,
)
from morpho_stress.backtest.runner import (
    BacktestVerdict,
    CriterionResult,
    format_verdict,
    run_backtest,
)
from morpho_stress.backtest.slippage_fit import (
    FitResult,
    fit_from_subgraph_export,
    fit_with_diagnostics,
    synthesize_uniswap_swaps,
)

__all__ = [
    "BacktestVerdict",
    "CriterionResult",
    "EventFixture",
    "EventMeta",
    "FitResult",
    "MarketProfile",
    "MarketRiskAssessment",
    "assess_all_markets",
    "assess_market",
    "calibrated_outflow_alpha",
    "current_markets",
    "fit_from_subgraph_export",
    "fit_with_diagnostics",
    "format_verdict",
    "hqla_v03",
    "lcr_onchain_v03",
    "list_fixtures",
    "load_event",
    "position_recovery_value",
    "run_backtest",
    "synthesize_uniswap_swaps",
]
