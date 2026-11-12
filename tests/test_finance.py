"""Tests for runtime.finance (requires pandas)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

from runtime.finance import (
    ChartOfAccounts,
    analyze,
    attach_lines,
    build_pnl,
    compare,
    draft_commentary,
    load_ledger,
    price_volume_mix,
    validate_ledger,
)
from runtime.finance.__main__ import main as cli_main
from runtime.finance.ledger import parse_amount

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "finance"))
from generate_sample_data import build_budget, build_gl


@pytest.fixture()
def gl() -> pd.DataFrame:
    return build_gl()


# ---------------------------------------------------------------- loader


def test_parse_amount_accounting_formats() -> None:
    s = pd.Series(["1,234.50", "(200)", "300-", "", "$1,000", "1.234,56", None])
    assert parse_amount(s).tolist() == [1234.5, -200.0, -300.0, 0.0, 1000.0, 1234.56, 0.0]


def test_load_ledger_detects_columns_and_signs(gl: pd.DataFrame) -> None:
    ledger, report = load_ledger(gl)
    assert report.column_map["account"] == "Account"
    assert report.column_map["entry_id"] == "JE No"
    assert set(ledger["period"]) == {"2026-07", "2026-08", "2026-09"}
    # Balanced GL nets to zero.
    assert abs(ledger["amount"].sum()) < 0.01


def test_load_ledger_vietnamese_headers() -> None:
    raw = pd.DataFrame({"Ngày": ["2026-09-01"], "Số tài khoản": ["5111"],
                        "Phát sinh nợ": ["0"], "Phát sinh có": ["1.000.000,00"]})
    ledger, report = load_ledger(raw)
    assert report.column_map["account"] == "Số tài khoản"
    assert ledger.loc[0, "amount"] == -1_000_000.0


def test_load_ledger_requires_account() -> None:
    with pytest.raises(ValueError, match="account column"):
        load_ledger(pd.DataFrame({"foo": [1], "amount": [1]}))


# ---------------------------------------------------------------- CoA


@pytest.mark.parametrize(("acct", "name", "line", "source"), [
    ("4000", "", "revenue", "range"),
    ("4900", "", "contra_revenue", "range"),
    ("6800", "", "depreciation_amortization", "range"),
    ("ABC", "Google Ads spend - marketing", "opex_sales_marketing", "keyword"),
    ("ZZZ", "Mystery", None, "unmapped"),
])
def test_generic_scheme(acct: str, name: str, line: str | None, source: str) -> None:
    m = ChartOfAccounts("generic").classify(acct, name)
    assert (m.line, m.source) == (line, source)


@pytest.mark.parametrize(("acct", "line"), [
    ("5111", "revenue"), ("521", "contra_revenue"), ("632", "cogs"), ("6421", "opex_personnel"),
    ("6427", "opex_ga"), ("6414", "depreciation_amortization"), ("635", "interest_expense"),
    ("8211", "income_tax"), ("131", "asset"), ("331", "liability"), ("4111", "equity"),
])
def test_vas_scheme(acct: str, line: str) -> None:
    assert ChartOfAccounts("vas").classify(acct).line == line


def test_explicit_mapping_wins() -> None:
    coa = ChartOfAccounts("generic", explicit={"4000": "other_income"})
    assert coa.classify("4000").source == "explicit"


# ---------------------------------------------------------------- validation


def test_validation_finds_planted_duplicate(gl: pd.DataFrame) -> None:
    ledger, _ = load_ledger(gl)
    mapping = ChartOfAccounts().classify_frame(ledger)
    codes = {f.code for f in validate_ledger(ledger, mapping).findings}
    assert "possible_duplicates" in codes
    assert "tb_out_of_balance" not in codes


def test_validation_flags_unbalanced_tb(gl: pd.DataFrame) -> None:
    ledger, _ = load_ledger(gl.iloc[1:])  # drop one leg
    report = validate_ledger(ledger)
    assert not report.ok
    assert {"tb_out_of_balance", "je_unbalanced"} <= {f.code for f in report.errors}


def test_pnl_only_extract_not_blocking(gl: pd.DataFrame) -> None:
    ledger, _ = load_ledger(gl[gl["Account"] >= "4000"])
    assert validate_ledger(ledger, expect_balanced=False).ok


# ---------------------------------------------------------------- P&L + variance


def test_pnl_subtotals_tie(gl: pd.DataFrame) -> None:
    ledger, _ = load_ledger(gl)
    mapped = attach_lines(ledger, ChartOfAccounts().classify_frame(ledger))
    pnl = build_pnl(mapped)
    sep = pnl["2026-09"]
    assert sep["gross_profit"] == pytest.approx(sep["net_revenue"] - sep["cogs"])
    # Net income must equal -(sum of all P&L net debits).
    pnl_amount = mapped[mapped["line"].isin(
        [k for k in pnl.index if pnl.loc[k, "kind"] == "line"])]
    expected = -pnl_amount[pnl_amount["period"] == "2026-09"]["amount"].sum()
    assert sep["net_income"] == pytest.approx(expected)


def test_compare_favorability_and_materiality() -> None:
    a = pd.Series({"revenue": 110_000.0, "cogs": 70_000.0, "opex_ga": 5_500.0})
    b = pd.Series({"revenue": 100_000.0, "cogs": 50_000.0, "opex_ga": 5_000.0})
    v = compare(a, b, materiality_abs=10_000, materiality_pct=10)
    assert v.loc["revenue", "direction"] == "F"
    assert v.loc["cogs", "direction"] == "U"
    assert v.loc["cogs", "material"]
    assert not v.loc["opex_ga", "material"]  # 10% but below abs threshold under AND rule


def test_compare_new_line_flag() -> None:
    v = compare(pd.Series({"opex_rnd": 20_000.0}), pd.Series({"opex_rnd": 0.0}))
    assert v.loc["opex_rnd", "flags"] == "new"
    assert math.isnan(v.loc["opex_rnd", "variance_pct"])


def test_price_volume_mix_reconciles() -> None:
    df = pd.DataFrame({
        "product": ["A", "B", "C"],
        "qty_actual": [120, 80, 10], "qty_baseline": [100, 100, 0],
        "rev_actual": [1320, 1600, 500], "rev_baseline": [1000, 2000, 0],
    })
    pvm = price_volume_mix(df)
    assert pvm["total"].sum() == pytest.approx(3420 - 3000)
    assert pvm.loc["C", "mix"] == 500  # new product


def test_commentary_never_invents_driver() -> None:
    v = compare(pd.Series({"opex_sales_marketing": 66_000.0}),
                pd.Series({"opex_sales_marketing": 26_000.0}))
    text = draft_commentary(v, "prior period")
    assert len(text) == 1 and "[DRIVER" in text[0]
    text = draft_commentary(v, drivers={"opex_sales_marketing": "Q3 campaign launch"})
    assert "Q3 campaign launch" in text[0] and "[DRIVER" not in text[0]


# ---------------------------------------------------------------- pipeline / CLI


def test_analyze_prior_period_with_gl_evidence(gl: pd.DataFrame) -> None:
    result = analyze(gl)
    assert result.period == "2026-09" and result.baseline_period == "2026-08"
    assert result.variance.loc["opex_sales_marketing", "material"]
    ev = result.evidence["opex_sales_marketing"]
    assert ev.iloc[0]["counterparty"] == "AdNetwork Co"
    assert ev.iloc[0]["change"] == pytest.approx(39_500)
    md = result.to_markdown()
    assert "## Data quality" in md and "AdNetwork Co" in md


def test_analyze_vs_budget(gl: pd.DataFrame) -> None:
    result = analyze(gl, budget=build_budget())
    v = result.variance
    assert v.loc["contra_revenue", "baseline"] == pytest.approx(-7_700)  # sign handled
    assert v.loc["opex_sales_marketing", "direction"] == "U"


def test_cli_exit_codes(tmp_path: Path, gl: pd.DataFrame) -> None:
    good = tmp_path / "gl.csv"
    gl.to_csv(good, index=False)
    assert cli_main(["--gl", str(good), "--out", str(tmp_path / "r.md")]) == 2  # dup warning
    bad = tmp_path / "bad.csv"
    gl.iloc[1:].to_csv(bad, index=False)
    assert cli_main(["--gl", str(bad), "--json"]) == 3
    assert cli_main(["--gl", str(tmp_path / "missing.csv")]) == 4
