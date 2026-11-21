"""Pre-analysis adjustments that real ERP exports need before a P&L is meaningful.

- ``exclude_closing_entries``: year/period-end closing JEs (VAS 911, income summary,
  closing to retained earnings) zero out P&L accounts; drop whole JEs that touch a
  closing account so revenue/expense balances survive.
- ``detect_cumulative``: flag YTD (cumulative) trial balances posing as monthly.
- ``ytd_to_periodic``: convert YTD balances to monthly movements (fiscal-year aware).
- ``currency_check``: block silent summing of different currencies.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

#: Default closing accounts per scheme (exact codes or prefixes).
DEFAULT_CLOSING_ACCOUNTS: dict[str, tuple[str, ...]] = {
    "vas": ("911",),
    "generic": (),  # varies by ERP; set `closing_accounts` in fpa-context
}

_CLOSING_WORDS = r"(?i)\b(closing|close to re|year[- ]end close|kết chuyển|ket chuyen|income summary)\b"


def exclude_closing_entries(
    ledger: pd.DataFrame,
    closing_accounts: tuple[str, ...] | list[str] = (),
    match_descriptions: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Drop every line of any JE that posts to a closing account (prefix match).

    Without entry ids, only the closing-account lines and lines whose description
    looks like a closing entry (when ``match_descriptions``) on the same date are
    dropped, and a warning is returned because pairing is uncertain.
    Returns (filtered ledger, info dict for reporting).
    """
    prefixes = tuple(str(a) for a in closing_accounts)
    info = {"closing_accounts": list(prefixes), "rows_removed": 0, "entries_removed": 0,
            "warning": None}
    if not prefixes:
        return ledger, info
    hits = ledger["account"].astype(str).str.startswith(prefixes)
    if not hits.any():
        return ledger, info
    has_ids = (ledger["entry_id"] != "").all()
    if has_ids:
        jes = set(ledger.loc[hits, "entry_id"])
        drop = ledger["entry_id"].isin(jes)
        info["entries_removed"] = len(jes)
    else:
        drop = hits.copy()
        if match_descriptions:
            dates = set(ledger.loc[hits, "date"].dropna())
            drop |= ledger["date"].isin(dates) & ledger["description"].str.contains(
                _CLOSING_WORDS, regex=True)
        info["warning"] = ("No journal-entry ids: closing lines removed by account"
                           + (" and description" if match_descriptions else "")
                           + " only; verify the P&L for the closing period.")
    info["rows_removed"] = int(drop.sum())
    logger.info("Removed %d closing-entry rows", info["rows_removed"])
    return ledger.loc[~drop].reset_index(drop=True), info


def detect_cumulative(ledger: pd.DataFrame, mapped_lines: pd.Series | None = None,
                      min_periods: int = 3, threshold: float = 0.8) -> bool:
    """Heuristic: a trial balance is YTD if, for >= ``threshold`` of P&L accounts,
    the absolute balance never decreases within a fiscal year.

    Only meaningful for one-row-per-account-period data (no dates). Detail G/L
    (with dates / many rows per account-period) returns False.
    """
    if ledger["date"].notna().any():
        return False
    df = ledger
    if mapped_lines is not None:
        df = df[mapped_lines.reindex(df.index).notna()]
    piv = df.pivot_table(index="account", columns="period", values="amount", aggfunc="sum")
    if piv.shape[1] < min_periods:
        return False
    years = pd.Index([str(c)[:4] for c in piv.columns])
    monotone = []
    for _, row in piv.abs().iterrows():
        ok = True
        for y in years.unique():
            seq = row[years == y].dropna().to_numpy()
            if len(seq) >= 2 and (seq[1:] < seq[:-1] - 0.005).any():
                ok = False
                break
        if row.dropna().nunique() > 1:
            monotone.append(ok)
    return bool(monotone) and sum(monotone) / len(monotone) >= threshold


def ytd_to_periodic(ledger: pd.DataFrame, fiscal_year_start_month: int = 1) -> pd.DataFrame:
    """Convert YTD balances (account x period) to monthly movements.

    The first month of each fiscal year keeps its YTD value; later months subtract
    the prior month. Missing months are treated as unchanged YTD (movement 0).
    """
    df = ledger.groupby(["account", "account_name", "period"], as_index=False)["amount"].sum()
    p = pd.PeriodIndex(df["period"], freq="M")
    df["_fy"] = p.year - (p.month < fiscal_year_start_month).astype(int)
    df = df.sort_values(["account", "period"])
    df["amount"] = df.groupby(["account", "_fy"])["amount"].diff().fillna(df["amount"])
    out = df.drop(columns="_fy")
    for col in ("date", "entry_id", "description", "cost_center", "counterparty", "currency"):
        out[col] = pd.NaT if col == "date" else ""
    out["debit"] = out["amount"].clip(lower=0)
    out["credit"] = (-out["amount"]).clip(lower=0)
    return out[ledger.columns].reset_index(drop=True)


def currency_check(ledger: pd.DataFrame) -> list[str]:
    """Distinct non-blank currencies present (len > 1 = blocking)."""
    if "currency" not in ledger.columns:
        return []
    return sorted({c for c in ledger["currency"].astype(str).str.upper().str.strip() if c})
