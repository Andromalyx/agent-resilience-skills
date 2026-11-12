"""End-to-end FP&A pipeline: load -> map -> validate -> P&L -> variance -> commentary.

Reasoning loop this mirrors (and the skill instructs the agent to follow):

    plan     : pick period + baseline (budget / prior), materiality
    tool     : load_ledger, ChartOfAccounts, validate_ledger, build_pnl, compare, drill_down
    observe  : validation findings gate how strongly results can be stated
    respond  : markdown pack with numbers, evidence, open items - no invented drivers
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from runtime.finance.coa import PNL_LINES, ChartOfAccounts, load_mapping_file
from runtime.finance.commentary import draft_commentary
from runtime.finance.kpis import pnl_kpis
from runtime.finance.ledger import LoadReport, load_ledger, natural_to_net_debit
from runtime.finance.pnl import attach_lines, build_pnl
from runtime.finance.validation import ValidationReport, validate_ledger
from runtime.finance.variance import compare_pnl, drill_down

logger = logging.getLogger(__name__)


@dataclass
class FinanceAnalysis:
    period: str
    baseline_name: str
    baseline_period: str | None
    load_report: LoadReport
    mapping: pd.DataFrame
    validation: ValidationReport
    pnl: pd.DataFrame
    variance: pd.DataFrame | None
    kpis: dict
    commentary: list[str]
    evidence: dict[str, pd.DataFrame] = field(default_factory=dict)
    budget_report: LoadReport | None = None

    @property
    def confidence(self) -> str:
        """How strongly results may be stated, derived from validation."""
        if not self.validation.ok:
            return "low - blocking data-quality errors; treat figures as provisional"
        if any(f.severity == "warning" for f in self.validation.findings):
            return "medium - usable with stated caveats"
        return "high - checks passed"

    def to_markdown(self) -> str:
        return render_markdown(self)


def analyze(
    gl: str | Path | pd.DataFrame,
    period: str | None = None,
    budget: str | Path | pd.DataFrame | None = None,
    scheme: str = "generic",
    mapping_file: str | Path | None = None,
    materiality_abs: float = 10_000,
    materiality_pct: float = 10.0,
    expect_balanced: bool = True,
    budget_sign: str = "natural",
    drill_by: str = "counterparty",
) -> FinanceAnalysis:
    """Run the full pipeline.

    Baseline is the budget for ``period`` if ``budget`` is given, otherwise the prior
    period present in the ledger.
    """
    ledger, load_report = load_ledger(gl)
    coa = ChartOfAccounts(scheme=scheme,
                          explicit=load_mapping_file(mapping_file) if mapping_file else None)
    mapping = coa.classify_frame(ledger)
    validation = validate_ledger(ledger, mapping, expect_balanced=expect_balanced)
    mapped = attach_lines(ledger, mapping)
    pnl = build_pnl(mapped)

    periods = sorted(p for p in mapped["period"].unique() if p not in {"ALL", "UNKNOWN"})
    period = period or (periods[-1] if periods else "ALL")
    if period not in pnl.columns:
        raise ValueError(f"Period {period!r} not in ledger periods {periods}")

    variance = None
    baseline_period = None
    baseline_name = "budget" if budget is not None else "prior period"
    budget_report = None
    evidence: dict[str, pd.DataFrame] = {}

    if budget is not None:
        bud, budget_report = load_ledger(budget, amount_sign=budget_sign)
        bud_map = coa.classify_frame(bud)
        if budget_sign == "natural":
            bud = natural_to_net_debit(bud, bud_map)
        bud_pnl = build_pnl(attach_lines(bud, bud_map))
        if period not in bud_pnl.columns:
            raise ValueError(f"Budget has no period {period!r}: {list(bud_pnl.columns[2:])}")
        baseline_period = period
        variance = compare_pnl(pnl, bud_pnl, period, period,
                               materiality_abs=materiality_abs, materiality_pct=materiality_pct)
    else:
        prior = [p for p in periods if p < period]
        if prior:
            baseline_period = prior[-1]
            variance = compare_pnl(pnl, pnl, period, baseline_period,
                                   materiality_abs=materiality_abs,
                                   materiality_pct=materiality_pct)
            # G/L evidence only possible period-over-period (budget has no transactions).
            for key in variance.index[variance["material"]]:
                if key in PNL_LINES:
                    accts = mapping.loc[mapping["line"] == key, "account"].tolist()
                    ev = drill_down(mapped, accts, period, baseline_period, by=drill_by, top_n=5)
                    if key in {"revenue", "other_income"}:
                        ev["change"] = -ev["change"]  # present income increases as positive
                    evidence[key] = ev

    commentary = (draft_commentary(variance, baseline_name, evidence)
                  if variance is not None else [])
    prior_col = baseline_period if budget is None else None
    kpis = pnl_kpis(pnl, period, prior=prior_col)

    return FinanceAnalysis(
        period=period, baseline_name=baseline_name, baseline_period=baseline_period,
        load_report=load_report, mapping=mapping, validation=validation, pnl=pnl,
        variance=variance, kpis=kpis, commentary=commentary, evidence=evidence,
        budget_report=budget_report,
    )


# --------------------------------------------------------------------------------------
# Rendering (no tabulate dependency)
# --------------------------------------------------------------------------------------

def _cell(x: object, pct: bool = False) -> str:
    if isinstance(x, (int, float)):
        if isinstance(x, float) and math.isnan(x):
            return ""
        if abs(x) < 0.5 and not pct:
            return "0"  # avoid "-0" from sign flips on empty lines
        return f"{x:,.1f}%" if pct else f"{x:,.0f}"
    return str(x)


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join("---" if i == 0 else "---:" for i in range(len(headers))) + "|"
    return "\n".join([line, sep] + ["| " + " | ".join(r) + " |" for r in rows])


def render_markdown(a: FinanceAnalysis) -> str:
    out: list[str] = [f"# P&L review - {a.period}", ""]
    out.append(f"**Baseline:** {a.baseline_name}"
               + (f" ({a.baseline_period})" if a.baseline_period else " (none available)"))
    out.append(f"**Confidence:** {a.confidence}")
    out.append(f"**Source:** {a.load_report.source} - {a.load_report.rows:,} rows")
    out.append("")

    # Data quality first: it gates how the numbers below may be used.
    out.append("## Data quality")
    if not a.validation.findings and not a.load_report.warnings:
        out.append("All checks passed.")
    for w in a.load_report.warnings:
        out.append(f"- [load] {w}")
    for f in a.validation.findings:
        out.append(f"- [{f.severity}] `{f.code}` {f.message}")
    out.append("")

    out.append("## P&L")
    cols = [c for c in a.pnl.columns if c not in {"label", "kind"}]
    rows = []
    for key, r in a.pnl.iterrows():
        pct = r["kind"] == "ratio"
        label = f"**{r['label']}**" if r["kind"] == "subtotal" else r["label"]
        rows.append([label] + [_cell(r[c], pct) for c in cols])
    out.append(_md_table(["Line"] + cols, rows))
    out.append("")

    if a.variance is not None:
        out.append(f"## Variance - {a.period} vs {a.baseline_name}")
        rows = []
        for key, r in a.variance.iterrows():
            is_pp = r["flags"] == "pp"
            var = f"{r['variance']:+.1f}pp" if is_pp else _cell(r["variance"])
            rows.append([
                r["label"], _cell(r["actual"], is_pp), _cell(r["baseline"], is_pp), var,
                "" if is_pp else _cell(r["variance_pct"], True), r["direction"],
                "Y" if r["material"] else "", "" if is_pp else r["flags"],
            ])
        out.append(_md_table(["Line", "Actual", "Baseline", "Var", "Var %", "F/U",
                              "Material", "Flags"], rows))
        out.append("")
        out.append("## Commentary draft (evidence-bound)")
        out.extend(f"- {c}" for c in a.commentary) if a.commentary else out.append(
            "No variance breached materiality.")
        out.append("")

    out.append("## KPIs")
    for k, v in a.kpis.items():
        out.append(f"- {k}: {_cell(v)}" if "pct" not in k else f"- {k}: {_cell(v, True)}")
    out.append("")
    out.append("## Open items before sign-off")
    items = [f"Resolve `{f.code}`: {f.message}" for f in a.validation.findings
             if f.severity in {"error", "warning"}]
    if any("[DRIVER" in c for c in a.commentary):
        items.append("Confirm business drivers for material variances with budget owners.")
    out.extend(f"- [ ] {i}" for i in items) if items else out.append("- None identified.")
    return "\n".join(out) + "\n"
