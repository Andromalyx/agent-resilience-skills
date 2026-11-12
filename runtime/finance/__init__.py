"""FP&A / accounting toolkit: G/L + trial balance -> P&L, variance, KPIs, commentary.

Requires pandas (``pip install -e ".[finance]"``).
"""

from runtime.finance.anomaly import (
    account_period_outliers,
    benford_first_digit,
    risk_rank,
    transaction_flags,
)
from runtime.finance.coa import ChartOfAccounts, load_mapping_file
from runtime.finance.commentary import draft_commentary
from runtime.finance.forecast import (
    DriverModel,
    ForecastResult,
    auto_forecast,
    forecast_pnl,
    seasonality_index,
)
from runtime.finance.kpis import (
    WorkingCapitalInputs,
    kpi_alerts,
    pnl_kpis,
    revenue_concentration,
    run_rate,
    runway_months,
    working_capital_kpis,
)
from runtime.finance.ledger import load_ledger, natural_to_net_debit
from runtime.finance.pipeline import FinanceAnalysis, analyze
from runtime.finance.pnl import account_detail, attach_lines, build_pnl, pnl_from_lines
from runtime.finance.reconcile import ReconResult, reconcile
from runtime.finance.scenarios import (
    Scenario,
    apply_scenario,
    breakeven_revenue,
    run_scenarios,
    sensitivity,
)
from runtime.finance.validation import validate_ledger
from runtime.finance.variance import compare, compare_pnl, drill_down, price_volume_mix

__all__ = [
    "ChartOfAccounts",
    "DriverModel",
    "FinanceAnalysis",
    "ForecastResult",
    "ReconResult",
    "Scenario",
    "WorkingCapitalInputs",
    "account_detail",
    "account_period_outliers",
    "analyze",
    "apply_scenario",
    "attach_lines",
    "auto_forecast",
    "benford_first_digit",
    "breakeven_revenue",
    "build_pnl",
    "compare",
    "compare_pnl",
    "draft_commentary",
    "drill_down",
    "forecast_pnl",
    "kpi_alerts",
    "load_ledger",
    "load_mapping_file",
    "natural_to_net_debit",
    "pnl_from_lines",
    "pnl_kpis",
    "price_volume_mix",
    "reconcile",
    "revenue_concentration",
    "risk_rank",
    "run_rate",
    "run_scenarios",
    "runway_months",
    "seasonality_index",
    "sensitivity",
    "transaction_flags",
    "validate_ledger",
    "working_capital_kpis",
]
