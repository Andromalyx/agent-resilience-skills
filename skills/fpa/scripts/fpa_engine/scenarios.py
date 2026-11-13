"""What-if scenarios and sensitivity (tornado) analysis on P&L lines.

Shocks are applied to *line totals* and subtotals are recomputed with the same
formulas as the actual P&L (``pnl_from_lines``), so scenario numbers always tie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .coa import PNL_LINES
from .pnl import pnl_from_lines


@dataclass(frozen=True)
class Scenario:
    """Named set of shocks. ``pct``: {line: +0.05}; ``abs``: {line: +10_000}.

    Linked shocks: ``cogs_follows_revenue=True`` scales COGS with net revenue
    (keeps gross margin %), the usual assumption for volume-driven scenarios.
    """

    name: str
    pct: dict[str, float] = field(default_factory=dict)
    abs: dict[str, float] = field(default_factory=dict)
    cogs_follows_revenue: bool = True
    assumptions: str = ""


def _lines(pnl: pd.DataFrame, column: str) -> pd.Series:
    return pnl.loc[list(PNL_LINES), column].astype(float)


def apply_scenario(base_lines: pd.Series, sc: Scenario) -> pd.Series:
    """Return shocked line totals (presentation-signed)."""
    unknown = (set(sc.pct) | set(sc.abs)) - set(PNL_LINES)
    if unknown:
        raise KeyError(f"Unknown P&L lines in scenario {sc.name!r}: {sorted(unknown)}")
    out = base_lines.copy()
    for line, p in sc.pct.items():
        out[line] *= 1 + p
    for line, a in sc.abs.items():
        out[line] += a
    if sc.cogs_follows_revenue and "cogs" not in sc.pct and "cogs" not in sc.abs:
        base_rev = base_lines["revenue"] + base_lines["contra_revenue"]
        new_rev = out["revenue"] + out["contra_revenue"]
        if base_rev:
            out["cogs"] = base_lines["cogs"] * new_rev / base_rev
    return out


def run_scenarios(pnl: pd.DataFrame, column: str, scenarios: list[Scenario]) -> pd.DataFrame:
    """P&L for base + each scenario (columns), with labels."""
    base = _lines(pnl, column)
    cols = {"base": base}
    for sc in scenarios:
        cols[sc.name] = apply_scenario(base, sc)
    return pnl_from_lines(pd.DataFrame(cols))


def sensitivity(
    pnl: pd.DataFrame,
    column: str,
    lines: list[str] | None = None,
    shock: float = 0.10,
    target: str = "net_income",
) -> pd.DataFrame:
    """Tornado table: impact on ``target`` of +/- ``shock`` to each line (one at a time).

    COGS is NOT linked here, so each bar isolates one line.
    """
    base = _lines(pnl, column)
    base_target = pnl_from_lines(base.to_frame("v")).loc[target, "v"]
    lines = lines or [l for l in PNL_LINES if base[l] != 0]
    rows = []
    for line in lines:
        res = {}
        for sign in (-1, 1):
            sc = Scenario(f"{line}{sign:+d}", pct={line: sign * shock}, cogs_follows_revenue=False)
            res[sign] = pnl_from_lines(apply_scenario(base, sc).to_frame("v")).loc[target, "v"]
        rows.append({"line": line, "down": res[-1] - base_target, "up": res[1] - base_target})
    out = pd.DataFrame(rows)
    out["swing"] = (out["up"] - out["down"]).abs()
    out = out.sort_values("swing", ascending=False).reset_index(drop=True)
    out.attrs.update(target=target, base=base_target, shock=shock)
    return out


def breakeven_revenue(pnl: pd.DataFrame, column: str) -> float:
    """Net revenue at which EBIT = 0, assuming COGS variable and opex/D&A fixed."""
    v = pnl[column]
    if not v["net_revenue"]:
        return float("nan")
    cm_ratio = 1 - v["cogs"] / v["net_revenue"]
    fixed = v["total_opex"] + v["depreciation_amortization"]
    return float(fixed / cm_ratio) if cm_ratio > 0 else float("inf")
