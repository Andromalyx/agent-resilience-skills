"""FP&A / accounting toolkit: G/L + trial balance -> P&L, variance, KPIs, commentary.

Requires pandas (``pip install -e ".[finance]"``).
"""

from .adjustments import (
    currency_check,
    detect_cumulative,
    exclude_closing_entries,
    ytd_to_periodic,
)
from .anomaly import (
    account_period_outliers,
    benford_first_digit,
    risk_rank,
    transaction_flags,
)
from .coa import ChartOfAccounts, load_mapping_file
from .commentary import draft_commentary
from .context import FinanceContext, load_context, record_driver
from .forecast import (
    DriverModel,
    ForecastResult,
    auto_forecast,
    forecast_pnl,
    seasonality_index,
)
from .kpis import (
    WorkingCapitalInputs,
    kpi_alerts,
    pnl_kpis,
    revenue_concentration,
    run_rate,
    runway_months,
    working_capital_kpis,
)
from .ledger import load_ledger, natural_to_net_debit
from .pipeline import FinanceAnalysis, analyze
from .pnl import account_detail, attach_lines, build_pnl, pnl_from_lines
from .reconcile import ReconResult, reconcile
from .scenarios import (
    Scenario,
    apply_scenario,
    breakeven_revenue,
    run_scenarios,
    sensitivity,
)
from .validation import validate_ledger
from .variance import compare, compare_pnl, drill_down, price_volume_mix

__all__ = [
    "ChartOfAccounts",
    "DriverModel",
    "FinanceAnalysis",
    "FinanceContext",
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
    "currency_check",
    "detect_cumulative",
    "draft_commentary",
    "drill_down",
    "exclude_closing_entries",
    "forecast_pnl",
    "kpi_alerts",
    "load_context",
    "load_ledger",
    "load_mapping_file",
    "natural_to_net_debit",
    "pnl_from_lines",
    "pnl_kpis",
    "price_volume_mix",
    "reconcile",
    "record_driver",
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
    "ytd_to_periodic",
]
