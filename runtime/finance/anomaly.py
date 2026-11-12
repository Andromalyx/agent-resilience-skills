"""Anomaly detection on G/L data: rules + robust statistics + optional ML, then a
single ranked review queue.

Why a composite score: an ML model on 2M journal lines will flag thousands of rows,
but a reviewer can clear ~200. The useful output is a *ranked* list where risk is
weighted by money, with reasons per row (precision@k is the metric that matters).

Components
- ``benford_first_digit``  : Nigrini MAD conformity + chi-square (needs n >= 300).
- ``account_period_outliers``: account total vs its own history (robust z, median/MAD).
- ``transaction_flags``    : per-row rules (amount outlier in account, new counterparty,
                             round, weekend, period-end, near-duplicate).
- ``isolation_forest_scores``: optional (scikit-learn), unsupervised score per row.
- ``risk_rank``            : composite score x log-materiality -> top-k with reasons.
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BENFORD_P = np.log10(1 + 1 / np.arange(1, 10))
# Nigrini (2012) first-digit MAD thresholds.
NIGRINI_MAD = ((0.006, "close conformity"), (0.012, "acceptable conformity"),
               (0.015, "marginally acceptable"), (math.inf, "nonconformity"))
CHI2_CRIT_8DF_05 = 15.507

RULE_WEIGHTS = {
    "amount_outlier": 3.0,
    "near_duplicate": 3.0,
    "new_counterparty": 1.5,
    "period_end": 1.0,
    "round_amount": 1.0,
    "weekend": 0.5,
    "ml_outlier": 2.0,
}


def _robust_z(x: pd.Series, ref: pd.Series | None = None) -> pd.Series:
    """(x - median) / (1.4826 * MAD) using ``ref`` as the reference distribution."""
    ref = x if ref is None else ref
    med = ref.median()
    mad = (ref - med).abs().median() * 1.4826
    if not mad or np.isnan(mad):
        std = ref.std()
        mad = std if std and not np.isnan(std) else np.nan
    return (x - med) / mad


# ------------------------------------------------------------------ Benford


def benford_first_digit(amounts: pd.Series, min_n: int = 300) -> dict:
    """First-digit Benford test on |amounts| >= 10 (small values distort the test)."""
    a = amounts.abs()
    a = a[a >= 10]
    n = len(a)
    first = a.map(lambda v: int(f"{v:.6e}"[0]))
    obs = first.value_counts().reindex(range(1, 10), fill_value=0).to_numpy()
    if n == 0:
        return {"n": 0, "conclusion": "no data"}
    obs_p = obs / n
    mad = float(np.abs(obs_p - BENFORD_P).mean())
    chi2 = float(((obs - n * BENFORD_P) ** 2 / (n * BENFORD_P)).sum())
    conclusion = next(label for limit, label in NIGRINI_MAD if mad < limit)
    result = {
        "n": n, "mad": round(mad, 4), "conclusion": conclusion, "chi_square": round(chi2, 2),
        "chi_square_flag": chi2 > CHI2_CRIT_8DF_05,
        "by_digit": pd.DataFrame({"observed": obs_p.round(4), "expected": BENFORD_P.round(4)},
                                 index=range(1, 10)),
    }
    if n < min_n:
        result["warning"] = (f"n={n} < {min_n}: Benford result is not reliable; "
                             "do not draw conclusions from it.")
    return result


# ------------------------------------------------------------------ account level


def account_period_outliers(mapped: pd.DataFrame, period: str, z: float = 3.0,
                            min_history: int = 6, pnl_only: bool = True) -> pd.DataFrame:
    """Accounts whose ``period`` total is far from their own history (robust z).

    ``pnl_only``: balance-sheet accounts move with every transaction, so they are
    excluded by default (requires the ``line`` column from ``attach_lines``).
    """
    if pnl_only and "line" in mapped.columns:
        from runtime.finance.coa import PNL_LINES

        mapped = mapped[mapped["line"].isin(list(PNL_LINES))]
    tot = mapped.groupby(["account", "period"])["amount"].sum().unstack(fill_value=0.0)
    if period not in tot.columns:
        raise ValueError(f"{period!r} not in ledger")
    hist_cols = [c for c in tot.columns if c < period]
    if len(hist_cols) < min_history:
        return pd.DataFrame(columns=["account", "current", "hist_median", "robust_z"])
    rows = []
    for acct, r in tot.iterrows():
        hist = r[hist_cols]
        if (hist == 0).all() and r[period] == 0:
            continue
        rz = _robust_z(pd.Series([r[period]]), hist).iloc[0]
        if np.isnan(rz) and r[period] != hist.median():
            rz = math.inf  # flat history then a change
        if abs(rz) >= z:
            rows.append({"account": acct, "current": r[period], "hist_median": hist.median(),
                         "robust_z": round(float(rz), 2)})
    out = pd.DataFrame(rows, columns=["account", "current", "hist_median", "robust_z"])
    return out.sort_values("robust_z", key=np.abs, ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------ transaction level


def transaction_flags(mapped: pd.DataFrame, period: str | None = None, z: float = 3.5,
                      round_threshold: float = 10_000, period_end_days: int = 3,
                      dup_window_days: int = 7) -> pd.DataFrame:
    """Per-row boolean rule flags. History (all rows) is the reference; ``period``
    restricts which rows are returned."""
    df = mapped.copy()
    df["abs_amount"] = df["amount"].abs()
    flags = pd.DataFrame(index=df.index)

    # Amount outlier vs same-account history (robust z on log scale - amounts are skewed).
    logs = np.log1p(df["abs_amount"])
    flags["amount_outlier"] = (
        logs.groupby(df["account"]).transform(lambda s: _robust_z(s).abs() >= z if len(s) >= 8
                                              else pd.Series(False, index=s.index))
        .astype(bool)
    )
    # First time a counterparty appears on this account (only meaningful with history).
    has_cp = df["counterparty"] != ""
    order = df.sort_values(["date", "period"]).index
    first_seen = df.loc[order].groupby(["account", "counterparty"])["period"].transform("min")
    earliest = df["period"].min()
    flags["new_counterparty"] = has_cp & (first_seen.reindex(df.index) == df["period"]) & (
        df["period"] != earliest)

    flags["round_amount"] = (df["abs_amount"] >= round_threshold) & (df["abs_amount"] % 1000 == 0)
    dated = df["date"].notna()
    flags["weekend"] = dated & (df["date"].dt.dayofweek >= 5)
    month_end = df["date"] + pd.offsets.MonthEnd(0)
    flags["period_end"] = dated & ((month_end - df["date"]).dt.days < period_end_days)

    # Near-duplicate: same account + counterparty + amount within N days, different JE or
    # identical JE repeated (exact dups are caught by validation; this catches re-keys).
    flags["near_duplicate"] = False
    key_cols = ["account", "counterparty", "amount"]
    for _, g in df[dated & (df["amount"] != 0)].groupby(key_cols):
        if len(g) < 2:
            continue
        g = g.sort_values("date")
        gaps = g["date"].diff().dt.days
        hit = gaps.notna() & (gaps <= dup_window_days)
        idx = g.index[hit | hit.shift(-1, fill_value=False)]
        flags.loc[idx, "near_duplicate"] = True

    out = pd.concat([df, flags], axis=1)
    return out if period is None else out[out["period"] == period]


def isolation_forest_scores(mapped: pd.DataFrame, contamination: float = 0.01,
                            random_state: int = 0) -> pd.Series | None:
    """Optional unsupervised score (higher = more anomalous). None if sklearn missing."""
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        logger.info("scikit-learn not installed; skipping IsolationForest")
        return None
    df = mapped
    feats = pd.DataFrame({
        "log_amt": np.log1p(df["amount"].abs()),
        "sign": np.sign(df["amount"]),
        "dow": df["date"].dt.dayofweek.fillna(-1),
        "dom": df["date"].dt.day.fillna(-1),
        "acct_freq": df.groupby("account")["account"].transform("count"),
        "cp_freq": df.groupby("counterparty")["counterparty"].transform("count"),
    })
    model = IsolationForest(contamination=contamination, random_state=random_state)
    model.fit(feats)
    return pd.Series(-model.score_samples(feats), index=df.index, name="ml_score")


def risk_rank(mapped: pd.DataFrame, period: str | None = None, top_k: int = 25,
              use_ml: bool = True, pnl_only: bool = True, min_rule_score: float = 1.0,
              **flag_kwargs) -> pd.DataFrame:
    """Ranked review queue: rule weights (+ ML) x log10(materiality), with reasons.

    ``pnl_only`` keeps the P&L leg of each entry (the offsetting AP/cash leg adds no
    information); ``min_rule_score`` drops weak single signals like a weekend date.
    """
    f = transaction_flags(mapped, period=None, **flag_kwargs)
    rule_cols = [c for c in RULE_WEIGHTS if c in f.columns]
    if use_ml:
        ml = isolation_forest_scores(mapped)
        if ml is not None:
            f["ml_outlier"] = ml >= ml.quantile(0.99)
            rule_cols.append("ml_outlier")
    if period is not None:
        f = f[f["period"] == period]
    weights = pd.Series({c: RULE_WEIGHTS[c] for c in rule_cols})
    f["rule_score"] = f[rule_cols].astype(float).mul(weights).sum(axis=1)
    f["risk_score"] = f["rule_score"] * np.log10(f["abs_amount"].clip(lower=10))
    f["reasons"] = f[rule_cols].apply(lambda r: ", ".join(c for c in rule_cols if r[c]), axis=1)
    if pnl_only and "line" in f.columns:
        from runtime.finance.coa import PNL_LINES

        f = f[f["line"].isin(list(PNL_LINES))]
    f = f[f["rule_score"] >= min_rule_score].sort_values("risk_score", ascending=False)
    cols = ["date", "period", "entry_id", "account", "account_name", "counterparty",
            "description", "amount", "risk_score", "reasons"]
    return f[[c for c in cols if c in f.columns]].head(top_k).reset_index(drop=True)
