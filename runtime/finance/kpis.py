"""FP&A KPIs from the P&L and (optionally) balance-sheet balances.

Balance-sheet KPIs need ending balances for specific account groups; pass them
explicitly rather than guessing which accounts are AR/AP/inventory.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def _safe_div(n: float, d: float) -> float:
    return float(n) / float(d) if d not in (0, 0.0) and not pd.isna(d) else float("nan")


@dataclass(frozen=True)
class WorkingCapitalInputs:
    """Ending balances for one period (presentation sign: positive)."""

    accounts_receivable: float | None = None
    inventory: float | None = None
    accounts_payable: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    days_in_period: int = 30


def pnl_kpis(pnl: pd.DataFrame, period: str, prior: str | None = None) -> dict[str, float]:
    """Core P&L KPIs for ``period`` (and growth vs ``prior`` if given)."""
    v = pnl[period]
    k = {
        "net_revenue": v["net_revenue"],
        "gross_margin_pct": v["gross_margin_pct"],
        "ebitda_margin_pct": v["ebitda_margin_pct"],
        "net_margin_pct": v["net_margin_pct"],
        "opex_to_revenue_pct": _safe_div(v["total_opex"], v["net_revenue"]) * 100,
        "personnel_to_revenue_pct": _safe_div(v["opex_personnel"], v["net_revenue"]) * 100,
        "effective_tax_rate_pct": _safe_div(v["income_tax"], v["ebt"]) * 100,
    }
    if prior is not None and prior in pnl.columns:
        p = pnl[prior]
        k["revenue_growth_pct"] = _safe_div(v["net_revenue"] - p["net_revenue"],
                                            abs(p["net_revenue"])) * 100
        k["opex_growth_pct"] = _safe_div(v["total_opex"] - p["total_opex"],
                                         abs(p["total_opex"])) * 100
        # Operating leverage: %change EBIT / %change revenue.
        ebit_g = _safe_div(v["ebit"] - p["ebit"], abs(p["ebit"]))
        rev_g = _safe_div(v["net_revenue"] - p["net_revenue"], abs(p["net_revenue"]))
        k["operating_leverage"] = _safe_div(ebit_g, rev_g)
    return {key: (round(val, 4) if not np.isnan(val) else val) for key, val in k.items()}


def working_capital_kpis(pnl: pd.DataFrame, period: str, wc: WorkingCapitalInputs) -> dict:
    """DSO / DIO / DPO / CCC / current ratio. Missing inputs -> NaN (never imputed)."""
    v = pnl[period]
    rev, cogs, d = v["net_revenue"], v["cogs"], wc.days_in_period
    nan = float("nan")
    dso = _safe_div(wc.accounts_receivable, rev) * d if wc.accounts_receivable is not None else nan
    dio = _safe_div(wc.inventory, cogs) * d if wc.inventory is not None else nan
    dpo = _safe_div(wc.accounts_payable, cogs) * d if wc.accounts_payable is not None else nan
    current = (_safe_div(wc.current_assets, wc.current_liabilities)
               if wc.current_assets is not None and wc.current_liabilities is not None else nan)
    return {"dso_days": dso, "dio_days": dio, "dpo_days": dpo,
            "cash_conversion_cycle_days": dso + dio - dpo, "current_ratio": current}


def run_rate(pnl: pd.DataFrame, row: str, periods: list[str], annualize: int = 12) -> float:
    """Average of the last ``periods`` x ``annualize`` (e.g., 3-month revenue run-rate)."""
    return float(pnl.loc[row, periods].mean() * annualize)
