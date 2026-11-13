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


# ------------------------------------------------------------------ concentration & runway


def revenue_concentration(mapped_ledger: pd.DataFrame, periods: list[str] | None = None,
                          by: str = "counterparty") -> pd.DataFrame:
    """Revenue share by customer + Herfindahl-Hirschman Index (HHI, 0-10,000).

    HHI < 1,500 diversified · 1,500-2,500 moderate · > 2,500 concentrated.
    Single customer > 25% = key-customer risk. Stored in ``.attrs``.
    """
    rev = mapped_ledger[mapped_ledger["line"] == "revenue"]
    if periods:
        rev = rev[rev["period"].isin(periods)]
    s = (-rev.groupby(rev[by].replace("", "(blank)"))["amount"].sum()).sort_values(ascending=False)
    total = s.sum()
    share = s / total * 100 if total else s * np.nan
    out = pd.DataFrame({"revenue": s, "share_pct": share.round(2),
                        "cumulative_pct": share.cumsum().round(2)})
    hhi = float((share ** 2).sum()) if total else float("nan")
    level = ("n/a" if np.isnan(hhi) else "low" if hhi < 1500
             else "moderate" if hhi <= 2500 else "high")
    out.attrs.update(hhi=round(hhi, 0), level=level,
                     top_customer_pct=float(share.iloc[0]) if len(share) else float("nan"))
    return out


def runway_months(cash: float, monthly_net_burn: float) -> float:
    """Months of cash at constant net burn (inf when cash-flow positive)."""
    return float("inf") if monthly_net_burn <= 0 else cash / monthly_net_burn


#: Default KPI alert thresholds (override per business; these are generic heuristics).
DEFAULT_ALERTS: dict[str, tuple[str, float, str]] = {
    "gross_margin_pct": ("<", 30.0, "Gross margin below 30% - pricing / COGS pressure"),
    "ebitda_margin_pct": ("<", 10.0, "EBITDA margin below 10%"),
    "net_margin_pct": ("<", 0.0, "Loss-making period"),
    "opex_to_revenue_pct": (">", 60.0, "Opex above 60% of revenue"),
    "revenue_growth_pct": ("<", -5.0, "Revenue down more than 5% period-over-period"),
    "opex_growth_pct": (">", 15.0, "Opex grew more than 15% period-over-period"),
}


def kpi_alerts(kpis: dict[str, float],
               thresholds: dict[str, tuple[str, float, str]] | None = None) -> list[str]:
    """Rule-based health flags. Missing/NaN KPIs never trigger an alert."""
    alerts = []
    for key, (op, limit, msg) in (thresholds or DEFAULT_ALERTS).items():
        v = kpis.get(key)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        if (op == "<" and v < limit) or (op == ">" and v > limit):
            alerts.append(f"{msg} ({key} = {v:,.1f})")
    return alerts
