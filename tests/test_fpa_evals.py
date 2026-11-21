"""Keep skills/fpa/evals/evals.json consistent with the files and the engine's numbers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.finance import analyze, run_scenarios
from runtime.finance.scenarios import Scenario

ROOT = Path(__file__).resolve().parents[1]
EVALS = json.loads((ROOT / "skills/fpa/evals/evals.json").read_text(encoding="utf-8"))["evals"]
GL = ROOT / "examples/finance/sample_gl.csv"
HIST = ROOT / "examples/finance/sample_gl_history.csv"


def test_eval_schema_and_files_exist() -> None:
    ids = [e["id"] for e in EVALS]
    assert len(ids) == len(set(ids))
    for e in EVALS:
        assert e["prompt"] and e["expected_output"] and len(e["assertions"]) >= 3
        for f in e["files"]:
            assert (ROOT / f).exists(), f


def test_eval1_numbers() -> None:
    a = analyze(GL)
    assert a.pnl.loc["net_income", "2026-09"] == pytest.approx(38_620, abs=1)
    assert a.variance.loc["net_income", "variance"] == pytest.approx(-43_675, abs=1)
    assert a.evidence["opex_sales_marketing"].iloc[0]["counterparty"] == "AdNetwork Co"


def test_eval2_numbers() -> None:
    a = analyze(GL, budget=ROOT / "examples/finance/sample_budget.csv")
    assert a.variance.loc["net_income", "baseline"] == pytest.approx(89_600)
    assert a.variance.loc["opex_sales_marketing", "baseline"] == pytest.approx(28_000)


def test_eval4_and_5_numbers() -> None:
    a = analyze(HIST, forecast_horizon=3)
    assert a.review_queue.iloc[0]["counterparty"] == "Zenith Advisory"
    assert a.account_outliers.iloc[0]["account"] == "6600"
    rev = a.forecast_detail["revenue"]
    assert rev.method == "holt_winters" and rev.backtest_wape[rev.method] < 10
    assert a.forecast.loc["net_revenue", "2026-12"] > a.forecast.loc["net_revenue", "2026-10"]


def test_eval6_numbers() -> None:
    a = analyze(HIST, anomalies=False)
    sc = run_scenarios(a.pnl, "2026-09", [Scenario("down", pct={"revenue": -0.1})])
    d_gp = sc.loc["gross_profit", "down"] - sc.loc["gross_profit", "base"]
    d_ebitda = sc.loc["ebitda", "down"] - sc.loc["ebitda", "base"]
    assert d_ebitda == pytest.approx(d_gp)
