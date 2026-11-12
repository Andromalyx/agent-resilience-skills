"""Tests for forecasting, anomaly detection, scenarios, reconciliation, concentration."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from runtime.finance import ChartOfAccounts, analyze, attach_lines, build_pnl, load_ledger
from runtime.finance.anomaly import (
    account_period_outliers,
    benford_first_digit,
    risk_rank,
    transaction_flags,
)
from runtime.finance.forecast import (
    DriverModel,
    auto_forecast,
    forecast_pnl,
    next_periods,
    seasonality_index,
)
from runtime.finance.kpis import kpi_alerts, revenue_concentration, runway_months
from runtime.finance.reconcile import reconcile, similarity
from runtime.finance.scenarios import Scenario, breakeven_revenue, run_scenarios, sensitivity

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "finance"))
from generate_sample_data import build_history

PERIOD = "2026-09"


@pytest.fixture(scope="module")
def mapped() -> pd.DataFrame:
    ledger, _ = load_ledger(build_history())
    return attach_lines(ledger, ChartOfAccounts().classify_frame(ledger))


@pytest.fixture(scope="module")
def pnl(mapped: pd.DataFrame) -> pd.DataFrame:
    return build_pnl(mapped)


def _periods(pnl: pd.DataFrame) -> list[str]:
    return [c for c in pnl.columns if c not in {"label", "kind"}]


# ---------------------------------------------------------------- forecasting


def test_next_periods_rolls_year() -> None:
    assert next_periods("2026-11", 3) == ["2026-12", "2027-01", "2027-02"]


def test_auto_forecast_picks_seasonal_method_and_q4_peak(pnl: pd.DataFrame) -> None:
    s = pnl.loc["net_revenue", _periods(pnl)].rename("net_revenue")
    r = auto_forecast(s, horizon=3)
    assert r.method in {"holt_winters", "seasonal_naive"}
    assert r.backtest_wape[r.method] == min(r.backtest_wape.values())
    assert r.point[2] > r.point[0]  # Dec above Oct
    assert (r.lower < r.point).all() and (r.upper > r.point).all()
    assert np.all(np.diff(r.upper - r.lower) >= -1e-9)  # intervals never narrow


def test_short_history_warns_and_excludes_seasonal() -> None:
    s = pd.Series([100.0, 110, 105, 120, 118], index=[f"2026-0{i}" for i in range(1, 6)])
    r = auto_forecast(s, horizon=2)
    assert r.method not in {"holt_winters", "seasonal_naive"}
    assert any("indicative" in w for w in r.warnings)


def test_forecast_pnl_subtotals_tie(pnl: pd.DataFrame) -> None:
    f, detail = forecast_pnl(pnl, horizon=2)
    col = f.columns[-1]
    assert f.loc["gross_profit", col] == pytest.approx(
        f.loc["net_revenue", col] - f.loc["cogs", col])
    assert "revenue" in detail


def test_seasonality_index(pnl: pd.DataFrame) -> None:
    si = seasonality_index(pnl.loc["net_revenue", _periods(pnl)])
    assert si["index"].idxmax() == 12 and si["index"].idxmin() == 2
    assert si.attrs["range_pts"] > 30


def test_driver_model() -> None:
    dm = DriverModel(
        periods=["2026-10", "2026-11"],
        lines={"revenue": ("units_x_price", "units", "price"),
               "cogs": ("pct_of", "revenue", 0.4),
               "opex_personnel": ("headcount_x_cost", "hc", "cost"),
               "opex_facilities": ("fixed", 10_000, 0.0)},
        drivers={"units": [100, 200], "price": 50, "hc": 2, "cost": 1_000},
    )
    p = dm.pnl()
    assert p.loc["gross_profit", "2026-11"] == pytest.approx(10_000 * 0.6)
    assert p.loc["ebitda", "2026-10"] == pytest.approx(5_000 * 0.6 - 2_000 - 10_000)
    with pytest.raises(ValueError):
        DriverModel(["a"], {"revenue": ("units_x_price", "u", "p")},
                    {"u": [1, 2], "p": 1}).pnl()


# ---------------------------------------------------------------- anomaly


def test_risk_rank_surfaces_planted_anomalies(mapped: pd.DataFrame) -> None:
    q = risk_rank(mapped, period=PERIOD, top_k=5, use_ml=False)
    assert q.iloc[0]["counterparty"] == "Zenith Advisory"
    assert "new_counterparty" in q.iloc[0]["reasons"]
    assert (q["reasons"].str.contains("near_duplicate")).sum() == 2
    assert (q["account"].str[0] >= "4").all()  # P&L legs only


def test_transaction_flags_period_filter(mapped: pd.DataFrame) -> None:
    f = transaction_flags(mapped, period=PERIOD)
    assert set(f["period"]) == {PERIOD}
    # Recurring vendors are not "new".
    assert not f.loc[f["counterparty"] == "Landlord LLC", "new_counterparty"].any()


def test_account_period_outliers(mapped: pd.DataFrame) -> None:
    out = account_period_outliers(mapped, PERIOD)
    assert out.iloc[0]["account"] == "6600"
    assert "2000" not in set(out["account"])  # balance sheet excluded


def test_benford_small_sample_warns() -> None:
    r = benford_first_digit(pd.Series([123.0, 456.0, 789.0] * 10))
    assert "warning" in r


def test_benford_conforming_data() -> None:
    rng = np.random.default_rng(0)
    r = benford_first_digit(pd.Series(10 ** rng.uniform(1, 6, 5_000)))
    assert r["conclusion"] in {"close conformity", "acceptable conformity"}


# ---------------------------------------------------------------- scenarios


def test_scenarios_and_sensitivity(pnl: pd.DataFrame) -> None:
    sc = run_scenarios(pnl, PERIOD, [Scenario("down", pct={"revenue": -0.1})])
    gm_base = sc.loc["gross_margin_pct", "base"]
    assert sc.loc["gross_margin_pct", "down"] == pytest.approx(gm_base)  # COGS linked
    assert sc.loc["net_revenue", "down"] < sc.loc["net_revenue", "base"]
    t = sensitivity(pnl, PERIOD, shock=0.1)
    assert t.iloc[0]["line"] == "revenue"
    with pytest.raises(KeyError):
        run_scenarios(pnl, PERIOD, [Scenario("bad", pct={"not_a_line": 0.1})])


def test_breakeven(pnl: pd.DataFrame) -> None:
    be = breakeven_revenue(pnl, PERIOD)
    assert 0 < be < pnl.loc["net_revenue", PERIOD]


# ---------------------------------------------------------------- reconciliation


def test_reconcile_tiers_and_balance_proof() -> None:
    gl = pd.DataFrame({
        "date": ["2026-09-01", "2026-09-03", "2026-09-05", "2026-09-07", "2026-09-07",
                 "2026-09-29"],
        "amount": [1000.0, -250.0, 400.0, 300.0, 200.0, 999.0],
        "reference": ["DEP1", "", "", "", "", ""],
        "description": ["deposit", "Acme supplies", "Beta Foods payment", "c1", "c2",
                        "in transit"],
    })
    bank = pd.DataFrame({
        "date": ["2026-09-01", "2026-09-04", "2026-09-10", "2026-09-08", "2026-09-30"],
        "amount": [1000.0, -250.0, 400.0, 500.0, -15.0],
        "reference": ["DEP1", "", "", "", ""],
        "description": ["DEP1", "ACME SUPPLIES LTD", "PMT BETA FOODS", "batch", "bank fee"],
    })
    r = reconcile(bank, gl, bank_ending_balance=10_000, gl_ending_balance=11_014)
    tiers = dict(zip(r.matches["bank_id"], r.matches["tier"]))
    assert tiers[0] == "exact" and tiers[1] == "amount_date"
    assert tiers[2] == "fuzzy" and tiers[3] == "one_to_many"
    assert r.summary["match_rate_pct"] == 80.0
    assert r.summary["unmatched_gl_total"] == 999.0
    assert r.summary["unmatched_bank_total"] == -15.0
    assert r.summary["reconciled"]


def test_similarity_normalizes_noise() -> None:
    assert similarity("PMT BETA FOODS LTD", "Beta Foods payment") > 0.9
    assert similarity("Acme", "Zenith") < 0.5


# ---------------------------------------------------------------- KPIs / pipeline


def test_revenue_concentration(mapped: pd.DataFrame) -> None:
    rc = revenue_concentration(mapped, [PERIOD])
    assert rc.attrs["level"] == "high" and rc.attrs["top_customer_pct"] > 45
    assert rc["cumulative_pct"].iloc[-1] == pytest.approx(100)


def test_kpi_alerts_and_runway() -> None:
    alerts = kpi_alerts({"gross_margin_pct": 20.0, "ebitda_margin_pct": float("nan")})
    assert len(alerts) == 1 and "Gross margin" in alerts[0]
    assert runway_months(120_000, 20_000) == 6
    assert runway_months(1, -5) == float("inf")


def test_pipeline_with_forecast_and_anomalies() -> None:
    a = analyze(build_history(), forecast_horizon=3, top_k=5)
    md = a.to_markdown()
    assert "## Anomaly screen" in md and "Zenith Advisory" in md
    assert "## Forecast (statistical baseline - not actuals)" in md
    assert list(a.forecast.columns[2:]) == ["2026-10", "2026-11", "2026-12"]
    assert any("Opex grew" in x for x in a.alerts)
