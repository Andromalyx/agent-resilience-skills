"""Build a management P&L from a mapped ledger or trial balance.

Presentation sign: income lines and subtotals are shown positive when profitable;
expense lines are shown positive as costs. Internally everything starts as net-debit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .coa import OPEX_LINES, PNL_LINES, is_income_line

#: (row_key, label, kind) in presentation order. kind: line | subtotal | ratio
PNL_LAYOUT: tuple[tuple[str, str, str], ...] = (
    ("revenue", "Revenue", "line"),
    ("contra_revenue", "Discounts, returns & allowances", "line"),
    ("net_revenue", "Net revenue", "subtotal"),
    ("cogs", "Cost of goods sold", "line"),
    ("gross_profit", "Gross profit", "subtotal"),
    ("gross_margin_pct", "Gross margin %", "ratio"),
    ("opex_personnel", "Personnel / payroll", "line"),
    ("opex_sales_marketing", "Sales & marketing", "line"),
    ("opex_rnd", "Research & development", "line"),
    ("opex_facilities", "Rent & facilities", "line"),
    ("opex_ga", "General & administrative", "line"),
    ("total_opex", "Total operating expenses", "subtotal"),
    ("ebitda", "EBITDA", "subtotal"),
    ("ebitda_margin_pct", "EBITDA margin %", "ratio"),
    ("depreciation_amortization", "Depreciation & amortization", "line"),
    ("ebit", "Operating income (EBIT)", "subtotal"),
    ("other_income", "Other / financial income", "line"),
    ("interest_expense", "Interest & financial expense", "line"),
    ("other_expense", "Other expense", "line"),
    ("ebt", "Profit before tax", "subtotal"),
    ("income_tax", "Income tax", "line"),
    ("net_income", "Net income", "subtotal"),
    ("net_margin_pct", "Net margin %", "ratio"),
)

INCOME_ROWS = {"revenue", "contra_revenue", "net_revenue", "gross_profit", "ebitda", "ebit",
               "other_income", "ebt", "net_income"}


def attach_lines(ledger: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """Join CoA lines + mapping source onto ledger rows."""
    m = mapping[["account", "line", "source"]].rename(columns={"source": "map_source"})
    return ledger.merge(m, on="account", how="left")


def line_totals(mapped_ledger: pd.DataFrame, by: str = "period") -> pd.DataFrame:
    """Presentation-signed totals per P&L line (rows) x ``by`` (columns).

    Income lines are flipped to positive; contra-revenue stays negative (it reduces
    revenue); expenses stay positive.
    """
    pnl_rows = mapped_ledger[mapped_ledger["line"].isin(PNL_LINES)]
    pivot = pnl_rows.pivot_table(index="line", columns=by, values="amount", aggfunc="sum",
                                 fill_value=0.0)
    pivot = pivot.reindex(list(PNL_LINES), fill_value=0.0)
    income_mask = [is_income_line(line) for line in pivot.index]
    pivot.loc[income_mask] = -pivot.loc[income_mask]
    return pivot


def build_pnl(mapped_ledger: pd.DataFrame, by: str = "period") -> pd.DataFrame:
    """Return the full P&L (lines, subtotals, margins) with a ``label`` column."""
    return pnl_from_lines(line_totals(mapped_ledger, by=by))


def pnl_from_lines(t: pd.DataFrame) -> pd.DataFrame:
    """Recompute subtotals/margins from presentation-signed line totals.

    ``t``: rows = P&L line keys (missing lines treated as 0), columns = periods or
    scenarios. Used by ``build_pnl``, forecasting, and scenario analysis so every
    view shares one set of formulas.
    """
    t = t.reindex(list(PNL_LINES), fill_value=0.0).astype(float)
    rows: dict[str, pd.Series] = {k: t.loc[k] for k in t.index}

    rows["net_revenue"] = rows["revenue"] + rows["contra_revenue"]
    rows["gross_profit"] = rows["net_revenue"] - rows["cogs"]
    rows["total_opex"] = sum((rows[k] for k in OPEX_LINES), start=pd.Series(0.0, index=t.columns))
    rows["ebitda"] = rows["gross_profit"] - rows["total_opex"]
    rows["ebit"] = rows["ebitda"] - rows["depreciation_amortization"]
    rows["ebt"] = (rows["ebit"] + rows["other_income"] - rows["interest_expense"]
                   - rows["other_expense"])
    rows["net_income"] = rows["ebt"] - rows["income_tax"]

    denom = rows["net_revenue"].replace(0, np.nan)  # avoid div/0 -> NaN, never inf
    rows["gross_margin_pct"] = rows["gross_profit"] / denom * 100
    rows["ebitda_margin_pct"] = rows["ebitda"] / denom * 100
    rows["net_margin_pct"] = rows["net_income"] / denom * 100

    out = pd.DataFrame({key: rows[key] for key, _, _ in PNL_LAYOUT}).T
    out.insert(0, "label", [label for _, label, _ in PNL_LAYOUT])
    out.insert(1, "kind", [kind for _, _, kind in PNL_LAYOUT])
    out.columns.name = None
    return out


def account_detail(mapped_ledger: pd.DataFrame, by: str = "period") -> pd.DataFrame:
    """Account-level presentation-signed totals, for drill-down under each line."""
    rows = mapped_ledger[mapped_ledger["line"].isin(PNL_LINES)].copy()
    sign = rows["line"].map(lambda l: -1.0 if is_income_line(l) else 1.0)
    rows["value"] = rows["amount"] * sign
    return rows.pivot_table(index=["line", "account", "account_name"], columns=by,
                            values="value", aggfunc="sum", fill_value=0.0)
