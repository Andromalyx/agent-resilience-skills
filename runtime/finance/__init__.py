"""FP&A / accounting toolkit: G/L + trial balance -> P&L, variance, KPIs, commentary.

Requires pandas (``pip install -e ".[finance]"``).
"""

from runtime.finance.coa import ChartOfAccounts, load_mapping_file
from runtime.finance.commentary import draft_commentary
from runtime.finance.kpis import WorkingCapitalInputs, pnl_kpis, run_rate, working_capital_kpis
from runtime.finance.ledger import load_ledger, natural_to_net_debit
from runtime.finance.pipeline import FinanceAnalysis, analyze
from runtime.finance.pnl import account_detail, attach_lines, build_pnl
from runtime.finance.validation import validate_ledger
from runtime.finance.variance import compare, compare_pnl, drill_down, price_volume_mix

__all__ = [
    "ChartOfAccounts",
    "FinanceAnalysis",
    "WorkingCapitalInputs",
    "account_detail",
    "analyze",
    "attach_lines",
    "build_pnl",
    "compare",
    "compare_pnl",
    "draft_commentary",
    "drill_down",
    "load_ledger",
    "load_mapping_file",
    "natural_to_net_debit",
    "pnl_kpis",
    "price_volume_mix",
    "run_rate",
    "validate_ledger",
    "working_capital_kpis",
]
