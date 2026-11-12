"""Evidence-bound variance commentary drafts.

The generator never invents business causes. It states the measured change, the
G/L evidence (top contributors), and leaves an explicit ``[DRIVER: confirm with
owner]`` placeholder unless a driver is supplied. This is the resilience skill's
anti-fabrication rule applied to FP&A narratives.
"""

from __future__ import annotations

import math

import pandas as pd

DRIVER_PLACEHOLDER = "[DRIVER: confirm with budget owner]"


def _fmt(x: float) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:,.0f}"


def _pct(x: float) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.1f}%"


def draft_line_commentary(
    key: str,
    row: pd.Series,
    baseline_name: str = "budget",
    evidence: pd.DataFrame | None = None,
    driver: str | None = None,
) -> str:
    """One commentary bullet for a material variance row from ``compare``."""
    label = row.get("label", key)
    fav = {"F": "favorable", "U": "unfavorable", "flat": "flat"}[row["direction"]]
    text = (
        f"**{label}**: {_fmt(row['actual'])} vs {baseline_name} {_fmt(row['baseline'])} "
        f"-> {_fmt(row['variance'])} ({_pct(row['variance_pct'])}), {fav}."
    )
    if row.get("flags"):
        text += f" Flags: {row['flags']}."
    if evidence is not None and not evidence.empty:
        by = evidence.columns[0]
        top = evidence.head(3)
        parts = [f"{r[by]} {_fmt(r['change'])}" for _, r in top.iterrows()]
        text += f" G/L evidence (top {by}): " + "; ".join(parts) + "."
    text += f" Driver: {driver}." if driver else f" Driver: {DRIVER_PLACEHOLDER}."
    return text


HEADLINE_ROWS = ("net_income", "ebitda")


def draft_commentary(
    variance: pd.DataFrame,
    baseline_name: str = "budget",
    evidence: dict[str, pd.DataFrame] | None = None,
    drivers: dict[str, str] | None = None,
    max_items: int = 8,
) -> list[str]:
    """Bullets for material variances: headline subtotals first, then the leaf P&L
    lines that explain them (largest first). Intermediate subtotals are skipped -
    they restate the same money and bury the driver.
    """
    from runtime.finance.coa import PNL_LINES

    evidence = evidence or {}
    drivers = drivers or {}
    mat = variance[variance["material"] & (variance["flags"] != "pp")]
    headline = [k for k in HEADLINE_ROWS if k in mat.index]
    leaves = mat[mat.index.isin(list(PNL_LINES))]
    leaves = leaves.reindex(leaves["variance"].abs().sort_values(ascending=False).index)
    keys = headline + list(leaves.index)
    return [
        draft_line_commentary(k, mat.loc[k], baseline_name, evidence.get(k), drivers.get(k))
        for k in keys[:max_items]
    ]
