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

from .adjustments import (
    DEFAULT_CLOSING_ACCOUNTS,
    currency_check,
    detect_cumulative,
    exclude_closing_entries,
    ytd_to_periodic,
)
from .anomaly import account_period_outliers, risk_rank
from .coa import PNL_LINES, ChartOfAccounts, load_mapping_file
from .commentary import draft_commentary
from .context import FinanceContext, load_context
from .forecast import ForecastResult, forecast_pnl
from .kpis import kpi_alerts, pnl_kpis, revenue_concentration
from .ledger import LoadReport, load_ledger, natural_to_net_debit
from .pnl import attach_lines, build_pnl
from .validation import Finding, ValidationReport, validate_ledger
from .variance import compare_pnl, drill_down

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
    alerts: list[str] = field(default_factory=list)
    concentration: pd.DataFrame | None = None
    review_queue: pd.DataFrame | None = None
    account_outliers: pd.DataFrame | None = None
    forecast: pd.DataFrame | None = None
    forecast_detail: dict[str, ForecastResult] = field(default_factory=dict)
    context: FinanceContext | None = None
    settings: dict = field(default_factory=dict)

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
    scheme: str | None = None,
    mapping_file: str | Path | None = None,
    materiality_abs: float | None = None,
    materiality_pct: float | None = None,
    expect_balanced: bool | None = None,
    budget_sign: str = "natural",
    drill_by: str = "counterparty",
    forecast_horizon: int = 0,
    anomalies: bool = True,
    top_k: int = 15,
    context: FinanceContext | str | Path | None = None,
    closing_accounts: tuple[str, ...] | list[str] | None = None,
    cumulative: bool | None = None,
    dayfirst: bool | None = None,
    decimal: str | None = None,
) -> FinanceAnalysis:
    """Run the full pipeline.

    Baseline is the budget for ``period`` if ``budget`` is given, otherwise the prior
    period present in the ledger. Arguments left as ``None`` come from ``context``
    (an ``fpa-context`` folder or ``FinanceContext``), then from safe defaults.
    """
    ctx = context if isinstance(context, FinanceContext) else load_context(context)
    scheme = scheme or ctx.scheme
    materiality_abs = ctx.materiality_abs if materiality_abs is None else materiality_abs
    materiality_pct = ctx.materiality_pct if materiality_pct is None else materiality_pct
    expect_balanced = ctx.expect_balanced if expect_balanced is None else expect_balanced
    cumulative = ctx.cumulative_tb if cumulative is None else cumulative
    dayfirst = ctx.dayfirst if dayfirst is None else dayfirst
    decimal = decimal or ctx.decimal
    if closing_accounts is None:
        closing_accounts = (ctx.closing_accounts if ctx.closing_accounts is not None
                            else DEFAULT_CLOSING_ACCOUNTS.get(scheme, ()))

    ledger, load_report = load_ledger(gl, dayfirst=dayfirst, decimal=decimal)
    pre_findings: list[Finding] = [Finding("error", "load_error", e) for e in load_report.errors]

    currencies = currency_check(ledger)
    if len(currencies) > 1:
        pre_findings.append(Finding(
            "error", "mixed_currency",
            f"Ledger mixes currencies {currencies}; totals are meaningless until amounts are "
            "in one functional currency (export functional-currency amounts or apply FX)."))
    elif (currencies and ctx.functional_currency
          and currencies[0] != ctx.functional_currency):
        pre_findings.append(Finding(
            "warning", "currency_mismatch",
            f"Ledger currency {currencies[0]} differs from functional currency "
            f"{ctx.functional_currency} in fpa-context."))

    ledger, closing_info = exclude_closing_entries(ledger, closing_accounts)
    if closing_info["rows_removed"]:
        pre_findings.append(Finding(
            "info", "closing_entries_removed",
            f"Removed {closing_info['rows_removed']} row(s) / {closing_info['entries_removed']} "
            f"closing JE(s) posting to {closing_info['closing_accounts']} so P&L balances "
            "are not zeroed."))
    if closing_info["warning"]:
        pre_findings.append(Finding("warning", "closing_entries_uncertain",
                                    closing_info["warning"]))

    explicit = dict(ctx.coa_map)
    if mapping_file:
        explicit.update(load_mapping_file(mapping_file))
    coa = ChartOfAccounts(scheme=scheme, explicit=explicit or None)
    mapping = coa.classify_frame(ledger)

    if cumulative is None and detect_cumulative(ledger):
        pre_findings.append(Finding(
            "warning", "possible_cumulative_tb",
            "P&L balances only grow within each year - this looks like a YTD (cumulative) "
            "trial balance. Monthly figures and variances are wrong unless converted: "
            "rerun with cumulative=True (--ytd) or set cumulative_tb in fpa-context."))
    elif cumulative:
        ledger = ytd_to_periodic(ledger, ctx.fiscal_year_start_month)
        pre_findings.append(Finding("info", "ytd_converted",
                                    "YTD balances converted to monthly movements."))

    if ctx.root is None:
        pre_findings.append(Finding(
            "info", "no_context",
            "No fpa-context folder used: CoA mapping, materiality, date/decimal format and "
            "drivers are defaults. Create one (`fpa.py init-context`) for real data."))
    typical = ledger["amount"].abs().median() if len(ledger) else 0
    if materiality_abs == 10_000 and typical > 1_000_000:
        pre_findings.append(Finding(
            "warning", "materiality_scale",
            f"Default materiality 10,000 vs typical posting {typical:,.0f}: almost every "
            "line will be 'material'. Set materiality in fpa-context (e.g. VND scale)."))

    validation = validate_ledger(ledger, mapping, expect_balanced=expect_balanced)
    validation.findings[:0] = pre_findings
    mapped = attach_lines(ledger, mapping)
    pnl = build_pnl(mapped)
    # Fall back to a populated dimension so G/L evidence is never all "(blank)".
    for dim in (drill_by, "counterparty", "description", "account"):
        if (mapped[dim].astype(str).str.strip() != "").any():
            drill_by = dim
            break

    periods = sorted(p for p in mapped["period"].unique() if p not in {"ALL", "UNKNOWN"})
    period = period or (periods[-1] if periods else "ALL")
    if period not in pnl.columns:
        raise ValueError(f"Period {period!r} not in ledger periods {periods}")

    variance = None
    baseline_period = None
    baseline_name = "budget" if budget is not None else "prior period"
    budget_report = None
    evidence: dict[str, pd.DataFrame] = {}
    rule = ctx.materiality_rule

    if budget is not None:
        bud, budget_report = load_ledger(budget, amount_sign=budget_sign, dayfirst=dayfirst,
                                         decimal=decimal)
        validation.findings.extend(Finding("error", "budget_load_error", e)
                                   for e in budget_report.errors)
        bud_map = coa.classify_frame(bud)
        if budget_sign == "natural":
            bud = natural_to_net_debit(bud, bud_map)
        bud_pnl = build_pnl(attach_lines(bud, bud_map))
        if period not in bud_pnl.columns:
            raise ValueError(f"Budget has no period {period!r}: {list(bud_pnl.columns[2:])}")
        baseline_period = period
        variance = compare_pnl(pnl, bud_pnl, period, period, materiality_abs=materiality_abs,
                               materiality_pct=materiality_pct, rule=rule)
    else:
        prior = [p for p in periods if p < period]
        if prior:
            baseline_period = prior[-1]
            variance = compare_pnl(pnl, pnl, period, baseline_period,
                                   materiality_abs=materiality_abs,
                                   materiality_pct=materiality_pct, rule=rule)
            # G/L evidence only possible period-over-period (budget has no transactions).
            for key in variance.index[variance["material"]]:
                if key in PNL_LINES:
                    accts = mapping.loc[mapping["line"] == key, "account"].tolist()
                    ev = drill_down(mapped, accts, period, baseline_period, by=drill_by, top_n=5)
                    if key in {"revenue", "other_income"}:
                        ev["change"] = -ev["change"]  # present income increases as positive
                    evidence[key] = ev

    drivers = {line: d for (p, line), d in ctx.drivers.items() if p == period}
    commentary = (draft_commentary(variance, baseline_name, evidence, drivers=drivers,
                                   owners=ctx.owners)
                  if variance is not None else [])
    prior_periods = [p for p in periods if p < period]
    kpis = pnl_kpis(pnl, period, prior=prior_periods[-1] if prior_periods else None)
    alerts = kpi_alerts(kpis, ctx.alert_thresholds)
    concentration = revenue_concentration(mapped, [period])

    review_queue = account_outliers = None
    if anomalies:
        review_queue = risk_rank(mapped, period=period, top_k=top_k)
        if ctx.whitelist_counterparties and not review_queue.empty:
            review_queue = review_queue[
                ~review_queue["counterparty"].isin(ctx.whitelist_counterparties)
            ].reset_index(drop=True)
        account_outliers = account_period_outliers(mapped, period)

    forecast = None
    forecast_detail: dict[str, ForecastResult] = {}
    if forecast_horizon:
        history = pnl[["label", "kind"] + [p for p in periods if p <= period]]
        forecast, forecast_detail = forecast_pnl(history, horizon=forecast_horizon)

    return FinanceAnalysis(
        period=period, baseline_name=baseline_name, baseline_period=baseline_period,
        load_report=load_report, mapping=mapping, validation=validation, pnl=pnl,
        variance=variance, kpis=kpis, commentary=commentary, evidence=evidence,
        budget_report=budget_report, alerts=alerts, concentration=concentration,
        review_queue=review_queue, account_outliers=account_outliers,
        forecast=forecast, forecast_detail=forecast_detail, context=ctx,
        settings={"scheme": scheme, "materiality": f"{materiality_abs:,.0f} {rule} "
                  f"{materiality_pct:g}%", "closing_accounts": list(closing_accounts),
                  "dayfirst": load_report.dayfirst, "decimal": load_report.decimal,
                  "context_sources": ctx.sources},
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
    st = a.settings
    if st:
        ctx = ", ".join(st["context_sources"]) or "none (defaults used)"
        order = {True: "dd/mm", False: "mm/dd", None: "n/a or ISO"}[st["dayfirst"]]
        out.append(f"**Settings:** scheme `{st['scheme']}` · materiality {st['materiality']} · "
                   f"dates {order} · decimal `{st['decimal']}` · closing accounts "
                   f"{st['closing_accounts'] or 'none'} · fpa-context: {ctx}")
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
    if a.concentration is not None and not a.concentration.empty:
        c = a.concentration.attrs
        out.append(f"- revenue concentration (HHI): {_cell(c['hhi'])} ({c['level']}); "
                   f"top customer {c['top_customer_pct']:.1f}%")
    if a.alerts:
        out.append("")
        out.append("**Alerts (rule-based, generic thresholds):**")
        out.extend(f"- {x}" for x in a.alerts)
    out.append("")

    if a.review_queue is not None:
        out.append(f"## Anomaly screen - {a.period} (ranked review queue)")
        if a.review_queue.empty:
            out.append("No rows flagged.")
        else:
            rows = [[str(r.get("date", ""))[:10], str(r["entry_id"]), str(r["account"]),
                     str(r["counterparty"]), _cell(float(r["amount"])),
                     f"{r['risk_score']:.1f}", str(r["reasons"])]
                    for _, r in a.review_queue.iterrows()]
            out.append(_md_table(["Date", "JE", "Account", "Counterparty", "Amount", "Score",
                                  "Reasons"], rows))
        if a.account_outliers is not None and not a.account_outliers.empty:
            out.append("")
            out.append("Account totals far from their own history (robust z):")
            out.extend(f"- {r['account']}: {_cell(r['current'])} vs median "
                       f"{_cell(r['hist_median'])} (z={r['robust_z']})"
                       for _, r in a.account_outliers.iterrows())
        out.append("Flags are review prompts, not conclusions of error or fraud.")
        out.append("")

    if a.forecast is not None:
        out.append("## Forecast (statistical baseline - not actuals)")
        fcols = [c for c in a.forecast.columns if c not in {"label", "kind"}]
        rows = []
        for key in ("net_revenue", "gross_profit", "total_opex", "ebitda", "net_income"):
            r = a.forecast.loc[key]
            rows.append([r["label"]] + [_cell(r[c]) for c in fcols])
        out.append(_md_table(["Line"] + fcols, rows))
        rev = a.forecast_detail.get("revenue")
        if rev:
            out.append(f"Revenue method: `{rev.method}` (backtest WAPE by method: "
                       f"{ {k: float(v) for k, v in rev.backtest_wape.items()} }); "
                       f"{int(rev.interval * 100)}% interval "
                       f"{_cell(float(rev.lower[0]))}-{_cell(float(rev.upper[0]))} for {rev.periods[0]}.")
            out.extend(f"- note: {w}" for w in rev.warnings)
        out.append("")
    out.append("## Open items before sign-off")
    items = [f"Resolve `{f.code}`: {f.message}" for f in a.validation.findings
             if f.severity in {"error", "warning"}]
    if any("[DRIVER" in c for c in a.commentary):
        items.append("Confirm business drivers for material variances with budget owners.")
    out.extend(f"- [ ] {i}" for i in items) if items else out.append("- None identified.")
    return "\n".join(out) + "\n"
