"""Data-quality and control checks on canonical ledger frames.

Every finding is evidence-backed (row counts + sample) so the agent reports *what* is
wrong instead of silently "fixing" it. Severity:

- ``error``   - numbers are unreliable until resolved (e.g., unbalanced entries).
- ``warning`` - numbers usable but caveated (e.g., unmapped accounts excluded).
- ``info``    - review flags, not errors (e.g., weekend postings, round amounts).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from runtime.finance.coa import PNL_LINES, is_income_line

TOLERANCE = 0.01  # currency units; rounding noise allowed when testing balance


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    count: int = 0
    sample: tuple[dict, ...] = field(default_factory=tuple)


@dataclass
class ValidationReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def ok(self) -> bool:
        """True when there are no blocking errors."""
        return not self.errors

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"severity": f.severity, "code": f.code, "count": f.count, "message": f.message}
             for f in self.findings],
            columns=["severity", "code", "count", "message"],
        )


def _sample(df: pd.DataFrame, n: int = 5) -> tuple[dict, ...]:
    cols = [c for c in ("date", "period", "entry_id", "account", "amount", "description")
            if c in df.columns]
    return tuple(df[cols].head(n).astype(str).to_dict("records"))


def validate_ledger(
    ledger: pd.DataFrame,
    mapping: pd.DataFrame | None = None,
    expect_balanced: bool = True,
    round_amount_threshold: float = 10_000,
) -> ValidationReport:
    """Run standard checks.

    Args:
        ledger: canonical frame from ``load_ledger``.
        mapping: output of ``ChartOfAccounts.classify_frame`` (enables mapping checks).
        expect_balanced: False for P&L-only extracts that legitimately won't net to zero.
        round_amount_threshold: flag round-thousand amounts at/above this size.
    """
    report = ValidationReport()
    if ledger.empty:
        report.add(Finding("error", "empty", "Ledger has no rows."))
        return report

    # 1. Trial balance per period: sum(debits) == sum(credits).
    by_period = ledger.groupby("period")["amount"].sum()
    off = by_period[by_period.abs() > TOLERANCE]
    if not off.empty:
        severity = "error" if expect_balanced else "info"
        detail = ", ".join(f"{p}: {v:,.2f}" for p, v in off.items())
        report.add(Finding(
            severity, "tb_out_of_balance",
            f"Debits != credits in {len(off)} period(s) ({detail}). "
            + ("Do not plug; find the missing/one-sided entries."
               if expect_balanced else "Expected for a P&L-only extract."),
            count=len(off),
        ))

    # 2. Journal entries balance individually.
    if (ledger["entry_id"] != "").any():
        je = ledger[ledger["entry_id"] != ""].groupby("entry_id")["amount"].sum()
        bad = je[je.abs() > TOLERANCE]
        if not bad.empty:
            rows = ledger[ledger["entry_id"].isin(bad.index)]
            report.add(Finding(
                "error" if expect_balanced else "warning", "je_unbalanced",
                f"{len(bad)} journal entr(ies) do not balance; total imbalance "
                f"{bad.sum():,.2f}.", count=len(bad), sample=_sample(rows),
            ))

    # 3. Exact duplicates (same date/account/amount/description/entry).
    key = ["date", "account", "amount", "description", "entry_id"]
    dups = ledger[ledger.duplicated(key, keep=False) & (ledger["amount"] != 0)]
    if not dups.empty:
        report.add(Finding(
            "warning", "possible_duplicates",
            f"{len(dups)} row(s) are exact duplicates; confirm they are not double posts.",
            count=len(dups), sample=_sample(dups),
        ))

    # 4. Zero / missing values.
    zeros = int((ledger["amount"] == 0).sum())
    if zeros:
        report.add(Finding("info", "zero_amount_rows", f"{zeros} zero-amount row(s).", zeros))

    # 5. Review flags on dated detail.
    if ledger["date"].notna().any():
        dated = ledger[ledger["date"].notna()]
        weekend = dated[dated["date"].dt.dayofweek >= 5]
        if not weekend.empty:
            report.add(Finding(
                "info", "weekend_postings",
                f"{len(weekend)} posting(s) dated on a weekend (review, not an error).",
                count=len(weekend), sample=_sample(weekend),
            ))
        mismatch = dated[dated["date"].dt.strftime("%Y-%m") != dated["period"]]
        if not mismatch.empty:
            report.add(Finding(
                "info", "date_period_mismatch",
                f"{len(mismatch)} row(s) have a posting date outside their period "
                "(accruals/late postings?).", count=len(mismatch), sample=_sample(mismatch),
            ))
    big_round = ledger[
        (ledger["amount"].abs() >= round_amount_threshold)
        & ((ledger["amount"].abs() % 1000) == 0)
    ]
    if not big_round.empty:
        report.add(Finding(
            "info", "round_amounts",
            f"{len(big_round)} round-thousand amount(s) >= {round_amount_threshold:,.0f} "
            "(estimates/manual JEs - confirm support).",
            count=len(big_round), sample=_sample(big_round),
        ))

    # 6. Mapping-dependent checks.
    if mapping is not None:
        _mapping_checks(ledger, mapping, report)
    return report


def _mapping_checks(ledger: pd.DataFrame, mapping: pd.DataFrame, report: ValidationReport) -> None:
    unmapped = mapping[mapping["source"] == "unmapped"]
    if not unmapped.empty:
        amt = ledger[ledger["account"].isin(unmapped["account"])]["amount"]
        report.add(Finding(
            "warning", "unmapped_accounts",
            f"{len(unmapped)} account(s) unmapped (net {amt.sum():,.2f}); excluded from P&L "
            f"until mapped: {', '.join(unmapped['account'].head(10))}.",
            count=len(unmapped),
        ))
    keyword = mapping[mapping["source"] == "keyword"]
    if not keyword.empty:
        report.add(Finding(
            "info", "keyword_mapped_accounts",
            f"{len(keyword)} account(s) mapped by name keyword only - confirm: "
            + ", ".join(f"{a}->{l}" for a, l in zip(keyword["account"].head(10),
                                                   keyword["line"].head(10))),
            count=len(keyword),
        ))

    # Abnormal balances: income accounts with net debit, expense accounts with net credit.
    lines = dict(zip(mapping["account"], mapping["line"]))
    bal = ledger.groupby(["period", "account"], as_index=False)["amount"].sum()
    bal["line"] = bal["account"].map(lines)
    bal = bal[bal["line"].isin(PNL_LINES) & (bal["line"] != "contra_revenue")]
    income = bal["line"].map(is_income_line)
    abnormal = bal[(income & (bal["amount"] > TOLERANCE)) | (~income & (bal["amount"] < -TOLERANCE))]
    if not abnormal.empty:
        report.add(Finding(
            "warning", "abnormal_balances",
            f"{len(abnormal)} account-period(s) carry an abnormal sign (e.g., negative "
            "expense). Check reversals, reclasses, or mis-postings.",
            count=len(abnormal), sample=_sample(abnormal),
        ))
