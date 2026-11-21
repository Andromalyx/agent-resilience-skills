"""Generate a deterministic, balanced sample G/L + budget for demos and tests.

Run: ``python examples/finance/generate_sample_data.py`` (writes next to this file).

Planted issues (so the toolkit has something real to find):
- Sep marketing spike from one vendor ("AdNetwork Co") -> material unfavorable variance.
- One duplicated software invoice in Sep -> ``possible_duplicates``.
- Postings on the 1st/5th/10th etc. that land on weekends -> ``weekend_postings`` info.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ACCOUNTS = {
    "1000": "Cash - Operating",
    "1200": "Accounts Receivable",
    "1500": "Accumulated Depreciation",
    "2000": "Accounts Payable",
    "2100": "Accrued Payroll",
    "2200": "Income Tax Payable",
    "4000": "Product Revenue",
    "4100": "Service Revenue",
    "4900": "Sales Discounts",
    "5000": "Cost of Goods Sold",
    "6000": "Salaries & Wages",
    "6200": "Digital Marketing",
    "6500": "Office Rent",
    "6600": "Software Subscriptions",
    "6800": "Depreciation Expense",
    "8100": "Interest Expense",
    "9000": "Income Tax Expense",
}

PERIODS = ["2026-07", "2026-08", "2026-09"]


def _je(rows: list, je_id: str, date: str, lines: list[tuple[str, float, str]], memo: str):
    """Append a balanced JE. lines: (account, net_debit, counterparty)."""
    assert abs(sum(a for _, a, _ in lines)) < 1e-6, f"unbalanced {je_id}"
    for acct, amt, cp in lines:
        rows.append({
            "Date": date, "JE No": je_id, "Account": acct, "Account Name": ACCOUNTS[acct],
            "Debit": round(max(amt, 0), 2), "Credit": round(max(-amt, 0), 2),
            "Memo": memo, "Name": cp, "Department": "HQ",
        })


def build_gl(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    n = 0
    for i, p in enumerate(PERIODS):
        growth = 1 + 0.04 * i
        # Revenue: three customers, product + service.
        for cust, base in (("Acme Retail", 180_000), ("Beta Foods", 120_000),
                           ("Cora Hotels", 60_000)):
            n += 1
            prod = round(base * growth * rng.uniform(0.97, 1.03), 2)
            svc = round(base * 0.15 * rng.uniform(0.95, 1.05), 2)
            disc = round(prod * 0.02, 2)
            _je(rows, f"JE{n:04d}", f"{p}-10", [
                ("1200", prod + svc - disc, cust), ("4900", disc, cust),
                ("4000", -prod, cust), ("4100", -svc, cust)], f"Invoice {cust} {p}")
            # COGS at ~42% of product revenue.
            n += 1
            cogs = round(prod * rng.uniform(0.41, 0.43), 2)
            _je(rows, f"JE{n:04d}", f"{p}-10", [("5000", cogs, cust), ("1000", -cogs, "")],
                f"COGS {cust} {p}")
        # Payroll.
        n += 1
        pay = round(95_000 * rng.uniform(0.99, 1.01), 2)
        _je(rows, f"JE{n:04d}", f"{p}-28", [("6000", pay, "Payroll"), ("2100", -pay, "Payroll")],
            f"Payroll {p}")
        # Marketing - planted Sep spike.
        n += 1
        mkt = 22_000.0 if p != "2026-09" else 61_500.0
        _je(rows, f"JE{n:04d}", f"{p}-15", [("6200", mkt, "AdNetwork Co"),
                                            ("2000", -mkt, "AdNetwork Co")],
            f"Paid social campaign {p}")
        n += 1
        _je(rows, f"JE{n:04d}", f"{p}-15", [("6200", 4_800.0, "SearchAds Inc"),
                                            ("2000", -4_800.0, "SearchAds Inc")],
            f"Search ads {p}")
        # Rent (posted on the 1st; 2026-08-01 is a Saturday -> weekend flag).
        n += 1
        _je(rows, f"JE{n:04d}", f"{p}-01", [("6500", 18_000.0, "Landlord LLC"),
                                            ("1000", -18_000.0, "Landlord LLC")], f"Rent {p}")
        # Software.
        n += 1
        sw = 7_350.0
        _je(rows, f"JE{n:04d}", f"{p}-05", [("6600", sw, "CloudSuite"),
                                            ("2000", -sw, "CloudSuite")], f"CloudSuite inv {p}")
        if p == "2026-09":  # planted duplicate: identical lines, same JE number
            _je(rows, f"JE{n:04d}", f"{p}-05", [("6600", sw, "CloudSuite"),
                                                ("2000", -sw, "CloudSuite")],
                f"CloudSuite inv {p}")
        # Depreciation, interest, tax.
        n += 1
        _je(rows, f"JE{n:04d}", f"{p}-30", [("6800", 6_000.0, ""), ("1500", -6_000.0, "")],
            f"Depreciation {p}")
        n += 1
        _je(rows, f"JE{n:04d}", f"{p}-30", [("8100", 2_150.0, "Bank"), ("1000", -2_150.0, "Bank")],
            f"Loan interest {p}")
        n += 1
        _je(rows, f"JE{n:04d}", f"{p}-30", [("9000", 25_000.0, ""), ("2200", -25_000.0, "")],
            f"Tax provision {p}")
    return pd.DataFrame(rows)


def build_budget() -> pd.DataFrame:
    """Natural-sign budget (revenue positive, costs positive) for Sep only."""
    lines = {"4000": 385_000, "4100": 54_000, "4900": 7_700, "5000": 160_000,
             "6000": 96_000, "6200": 28_000, "6500": 18_000, "6600": 7_500,
             "6800": 6_000, "8100": 2_200, "9000": 24_000}
    return pd.DataFrame([{"Account": a, "Account Name": ACCOUNTS[a], "Period": "2026-09",
                          "Amount": v} for a, v in lines.items()])


def build_history(months: int = 27, end: str = "2026-09", seed: int = 11) -> pd.DataFrame:
    """Longer, seasonal G/L for forecasting / anomaly demos.

    Seasonality: Q4 peak (Nov-Dec +25-35%), Feb trough. Planted anomalies in the last
    month: a one-off 48,000 round 'consulting' JE from a never-seen vendor posted on the
    last day of the month, and a re-keyed (near-duplicate) supplier invoice.
    """
    rng = np.random.default_rng(seed)
    season = {1: 0.95, 2: 0.85, 3: 0.95, 4: 1.0, 5: 1.0, 6: 1.02, 7: 0.98, 8: 0.97,
              9: 1.03, 10: 1.08, 11: 1.25, 12: 1.35}
    periods = [str(p) for p in pd.period_range(end=end, periods=months, freq="M")]
    rows: list[dict] = []
    n = 0
    for i, p in enumerate(periods):
        month = int(p[-2:])
        trend = 1 + 0.01 * i
        for cust, share in (("Acme Retail", 0.5), ("Beta Foods", 0.33), ("Cora Hotels", 0.17)):
            n += 1
            rev = round(360_000 * share * trend * season[month] * rng.uniform(0.97, 1.03), 2)
            _je(rows, f"H{n:05d}", f"{p}-12", [("1200", rev, cust), ("4000", -rev, cust)],
                f"Invoice {cust} {p}")
            n += 1
            cogs = round(rev * rng.uniform(0.41, 0.43), 2)
            _je(rows, f"H{n:05d}", f"{p}-12", [("5000", cogs, cust), ("1000", -cogs, "")],
                f"COGS {cust} {p}")
        for acct, vendor, base in (("6000", "Payroll", 95_000), ("6200", "AdNetwork Co", 24_000),
                                   ("6600", "CloudSuite", 7_350)):
            n += 1
            amt = round(base * rng.uniform(0.97, 1.03), 2)
            _je(rows, f"H{n:05d}", f"{p}-20", [(acct, amt, vendor), ("2000", -amt, vendor)],
                f"{vendor} {p}")
        n += 1
        _je(rows, f"H{n:05d}", f"{p}-03", [("6500", 18_000.0, "Landlord LLC"),
                                           ("1000", -18_000.0, "Landlord LLC")], f"Rent {p}")
    last = periods[-1]
    last_day = str((pd.Period(last, freq="M").end_time).date())
    n += 1
    _je(rows, f"H{n:05d}", last_day, [("6600", 48_000.0, "Zenith Advisory"),
                                      ("2000", -48_000.0, "Zenith Advisory")],
        "Consulting - strategy")
    n += 1
    _je(rows, f"H{n:05d}", f"{last}-22", [("6600", 7_412.55, "CloudSuite"),
                                          ("2000", -7_412.55, "CloudSuite")], "CloudSuite re-key")
    n += 1
    _je(rows, f"H{n:05d}", f"{last}-24", [("6600", 7_412.55, "CloudSuite"),
                                          ("2000", -7_412.55, "CloudSuite")], "CloudSuite inv")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    here = Path(__file__).parent
    build_gl().to_csv(here / "sample_gl.csv", index=False)
    build_budget().to_csv(here / "sample_budget.csv", index=False)
    build_history().to_csv(here / "sample_gl_history.csv", index=False)
    print(f"wrote sample_gl.csv, sample_budget.csv, sample_gl_history.csv to {here}")

