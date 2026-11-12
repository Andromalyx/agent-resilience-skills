"""Variance / flux analysis and G/L drill-down.

- ``compare``: actual vs budget / forecast / prior period at line or account level,
  with favorable/unfavorable logic and a materiality rule (abs AND/OR pct).
- ``drill_down``: which counterparties / memos / cost centers drove a change.
- ``price_volume_mix``: decompose a revenue (or cost) change into price, volume, mix.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from runtime.finance.pnl import INCOME_ROWS


def compare(
    actual: pd.Series,
    baseline: pd.Series,
    income_keys: set[str] | None = None,
    materiality_abs: float = 10_000,
    materiality_pct: float = 10.0,
    rule: str = "and",
    labels: pd.Series | None = None,
) -> pd.DataFrame:
    """Compare two presentation-signed series indexed by line/account key.

    Args:
        actual / baseline: values (income positive, costs positive).
        income_keys: keys where higher is better. Defaults to standard P&L income rows.
        materiality_abs / materiality_pct: thresholds.
        rule: ``and`` (both must be breached - common for flux) or ``or`` (either).
        labels: optional display labels indexed like ``actual``.

    Returns DataFrame: actual, baseline, variance, variance_pct, direction, material,
    flags (sign_flip / new / dropped).
    """
    income_keys = INCOME_ROWS if income_keys is None else income_keys
    idx = actual.index.union(baseline.index, sort=False)
    a = actual.reindex(idx).fillna(0.0).astype(float)
    b = baseline.reindex(idx).fillna(0.0).astype(float)

    var = a - b
    pct = (var / b.abs().replace(0, np.nan) * 100).to_numpy()  # NaN when baseline is 0
    higher_is_better = pd.Series([k in income_keys for k in idx], index=idx)
    favorable = np.where(higher_is_better, var >= 0, var <= 0)
    direction = np.where(var.abs() < 0.005, "flat", np.where(favorable, "F", "U"))

    abs_hit = var.abs() >= materiality_abs
    pct_hit = pd.Series(np.nan_to_num(np.abs(pct), nan=np.inf), index=idx) >= materiality_pct
    material = (abs_hit & pct_hit) if rule == "and" else (abs_hit | pct_hit)

    flags = []
    for av, bv in zip(a, b):
        f = []
        if bv == 0 and av != 0:
            f.append("new")
        elif av == 0 and bv != 0:
            f.append("dropped")
        elif np.sign(av) != np.sign(bv):
            f.append("sign_flip")
        flags.append(",".join(f))

    out = pd.DataFrame({
        "actual": a, "baseline": b, "variance": var, "variance_pct": pct,
        "direction": direction, "material": material.values, "flags": flags,
    }, index=idx)
    if labels is not None:
        out.insert(0, "label", labels.reindex(idx).fillna(pd.Series(idx, index=idx)))
    return out


def compare_pnl(
    pnl_actual: pd.DataFrame,
    pnl_baseline: pd.DataFrame,
    actual_col: str,
    baseline_col: str,
    **kwargs,
) -> pd.DataFrame:
    """Compare two ``build_pnl`` outputs (ratio rows compared in percentage points)."""
    lines = pnl_actual[pnl_actual["kind"] != "ratio"]
    base = pnl_baseline.loc[lines.index]
    out = compare(lines[actual_col], base[baseline_col], labels=lines["label"], **kwargs)
    # Margins: report the pp change but never mark material by the abs rule.
    ratios = pnl_actual[pnl_actual["kind"] == "ratio"]
    pp = ratios[actual_col] - pnl_baseline.loc[ratios.index, baseline_col]
    ratio_frame = pd.DataFrame({
        "label": ratios["label"], "actual": ratios[actual_col],
        "baseline": pnl_baseline.loc[ratios.index, baseline_col], "variance": pp,
        "variance_pct": np.nan, "direction": np.where(pp >= 0, "F", "U"),
        "material": False, "flags": "pp",
    })
    order = [k for k in pnl_actual.index]
    return pd.concat([out, ratio_frame]).loc[order]


def drill_down(
    mapped_ledger: pd.DataFrame,
    accounts: list[str] | None,
    period_actual: str,
    period_baseline: str,
    by: str = "counterparty",
    top_n: int = 10,
) -> pd.DataFrame:
    """Top contributors to the change between two periods for given accounts.

    Values are net-debit (expense increase = positive). Returns columns:
    ``<by>, baseline, actual, change, share_of_change``.
    """
    df = mapped_ledger
    if accounts:
        df = df[df["account"].isin(accounts)]
    df = df[df["period"].isin([period_actual, period_baseline])]
    key = df[by].replace("", "(blank)")
    piv = df.assign(_k=key).pivot_table(index="_k", columns="period", values="amount",
                                        aggfunc="sum", fill_value=0.0)
    for p in (period_actual, period_baseline):
        if p not in piv.columns:
            piv[p] = 0.0
    piv["change"] = piv[period_actual] - piv[period_baseline]
    total = piv["change"].sum()
    piv["share_of_change"] = piv["change"] / total * 100 if total else np.nan
    piv = piv.reindex(piv["change"].abs().sort_values(ascending=False).index).head(top_n)
    piv = piv.rename(columns={period_actual: "actual", period_baseline: "baseline"})
    piv.index.name = by
    return piv[["baseline", "actual", "change", "share_of_change"]].reset_index()


def price_volume_mix(
    df: pd.DataFrame,
    key: str = "product",
    qty_a: str = "qty_actual",
    qty_b: str = "qty_baseline",
    rev_a: str = "rev_actual",
    rev_b: str = "rev_baseline",
) -> pd.DataFrame:
    """Price / volume / mix decomposition (standard FP&A method).

    volume = (Q_a_total - Q_b_total) * avg_price_b
    mix    = sum((mix_a - mix_b) * Q_a_total * P_b)
    price  = sum((P_a - P_b) * Q_a)
    The three effects sum exactly to total revenue change (checked).
    """
    d = df.set_index(key)[[qty_a, qty_b, rev_a, rev_b]].astype(float)
    if (d[[qty_a, qty_b]] < 0).any().any():
        raise ValueError("Quantities must be non-negative.")
    p_a = (d[rev_a] / d[qty_a]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    p_b = (d[rev_b] / d[qty_b]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    qa_tot, qb_tot = d[qty_a].sum(), d[qty_b].sum()
    mix_a = d[qty_a] / qa_tot if qa_tot else 0.0
    mix_b = d[qty_b] / qb_tot if qb_tot else 0.0
    avg_p_b = d[rev_b].sum() / qb_tot if qb_tot else 0.0

    # Per-row: volume share allocated by baseline mix so rows sum to total.
    volume = (qa_tot - qb_tot) * mix_b * p_b
    mix = (mix_a - mix_b) * qa_tot * p_b
    price = (p_a - p_b) * d[qty_a]
    # Products new in actual (no baseline price): treat full revenue as mix/new.
    new = d[qty_b] == 0
    price = price.where(~new, 0.0)
    mix = mix.where(~new, d[rev_a])
    out = pd.DataFrame({"volume": volume, "mix": mix, "price": price})
    out["total"] = out.sum(axis=1)
    out["check"] = (d[rev_a] - d[rev_b]) - out["total"]
    if abs(out["check"].sum()) > 0.01:
        raise AssertionError(f"PVM does not reconcile: residual {out['check'].sum():.4f}")
    out.attrs["avg_price_baseline"] = avg_p_b
    return out.drop(columns="check")
