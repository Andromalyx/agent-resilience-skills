"""Bank / sub-ledger to G/L reconciliation with tiered matching.

Tiers (each locks matched rows before the next runs):
1. ``exact``     - same reference, amount within tolerance, date within window.
2. ``amount_date`` - amount within tolerance, date within window, unique candidate.
3. ``fuzzy``     - amount within tolerance, wider window, description similarity >= threshold.
4. ``one_to_many`` - one bank line = sum of up to ``max_group`` GL lines (batched deposits).

Every match records tier + score (auditors ask). Fuzzy and one-to-many matches above
``review_threshold`` are marked ``needs_review`` - they are proposals, not clearances.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import pandas as pd

_NOISE = re.compile(r"\b(payment|pmt|trf|transfer|ref|inv|invoice|ach|wire|pos|ltd|llc|inc|co)\b")


def normalize_text(text: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", str(text).lower())
    return " ".join(_NOISE.sub(" ", t).split())


def similarity(a: str, b: str) -> float:
    """Token-sorted similarity in [0, 1]; uses rapidfuzz if installed."""
    a, b = normalize_text(a), normalize_text(b)
    if not a or not b:
        return 0.0
    try:
        from rapidfuzz import fuzz

        return fuzz.token_set_ratio(a, b) / 100
    except ImportError:
        return SequenceMatcher(None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))).ratio()


@dataclass
class ReconResult:
    matches: pd.DataFrame
    unmatched_bank: pd.DataFrame
    unmatched_gl: pd.DataFrame
    summary: dict = field(default_factory=dict)


def _prep(df: pd.DataFrame, side: str) -> pd.DataFrame:
    need = {"date", "amount"}
    if missing := need - set(df.columns):
        raise ValueError(f"{side} missing columns {sorted(missing)}")
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for col in ("reference", "description"):
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str)
    out["amount"] = out["amount"].astype(float).round(2)
    out["_id"] = range(len(out))
    return out


def reconcile(
    bank: pd.DataFrame,
    gl: pd.DataFrame,
    amount_tol: float = 0.01,
    date_window: int = 3,
    fuzzy_window: int = 7,
    fuzzy_threshold: float = 0.8,
    max_group: int = 5,
    review_threshold: float = 1_000,
    bank_ending_balance: float | None = None,
    gl_ending_balance: float | None = None,
) -> ReconResult:
    """Match bank lines to GL cash lines. Sign: receipts positive on both sides
    (GL cash net-debit = bank deposit)."""
    b, g = _prep(bank, "bank"), _prep(gl, "gl")
    used_b: set[int] = set()
    used_g: set[int] = set()
    rows: list[dict] = []

    def _add(bi: int, gis: list[int], tier: str, score: float) -> None:
        used_b.add(bi)
        used_g.update(gis)
        amt = b.at[bi, "amount"]
        rows.append({"bank_id": bi, "gl_ids": gis, "tier": tier, "score": round(score, 3),
                     "amount": amt, "bank_date": b.at[bi, "date"],
                     "needs_review": tier in {"fuzzy", "one_to_many"} and abs(amt) >= review_threshold})

    def _candidates(bi: int, window: int) -> pd.DataFrame:
        r = b.loc[bi]
        c = g[~g["_id"].isin(used_g)]
        c = c[(c["amount"] - r["amount"]).abs() <= amount_tol]
        return c[(c["date"] - r["date"]).abs().dt.days <= window]

    # Tier 1: exact reference.
    for bi in b.index:
        ref = b.at[bi, "reference"].strip()
        if not ref:
            continue
        c = _candidates(bi, date_window)
        c = c[c["reference"].str.strip() == ref]
        if len(c):
            _add(bi, [int(c.index[0])], "exact", 1.0)
    # Tier 2: unique amount + date.
    for bi in b.index.difference(list(used_b)):
        c = _candidates(bi, date_window)
        if len(c) == 1:
            _add(bi, [int(c.index[0])], "amount_date", 0.9)
    # Tier 3: fuzzy description among multiple / wider-window candidates.
    for bi in b.index.difference(list(used_b)):
        c = _candidates(bi, fuzzy_window)
        if c.empty:
            continue
        bank_desc = b.at[bi, "description"]
        scores = c["description"].map(lambda d, ref=bank_desc: similarity(ref, d))
        best = scores.idxmax()
        if scores[best] >= fuzzy_threshold:
            _add(bi, [int(best)], "fuzzy", float(scores[best]))
    # Tier 4: one bank line = sum of several GL lines (subset-sum, capped).
    for bi in b.index.difference(list(used_b)):
        r = b.loc[bi]
        c = g[~g["_id"].isin(used_g)]
        c = c[((c["date"] - r["date"]).abs().dt.days <= fuzzy_window)
              & (c["amount"].abs() <= abs(r["amount"]) + amount_tol)
              & ((c["amount"] > 0) == (r["amount"] > 0))]
        if len(c) > 15:  # bound combinatorics
            c = c.reindex(c["amount"].sort_values(ascending=False).index[:15])
        found = None
        for k in range(2, min(max_group, len(c)) + 1):
            for combo in itertools.combinations(c.index, k):
                if abs(c.loc[list(combo), "amount"].sum() - r["amount"]) <= amount_tol:
                    found = [int(i) for i in combo]
                    break
            if found:
                break
        if found:
            _add(bi, found, "one_to_many", 0.7)

    matches = pd.DataFrame(rows, columns=["bank_id", "gl_ids", "tier", "score", "amount",
                                          "bank_date", "needs_review"])
    ub = b[~b.index.isin(list(used_b))].drop(columns="_id")
    ug = g[~g.index.isin(list(used_g))].drop(columns="_id")
    summary = {
        "bank_lines": len(b), "gl_lines": len(g),
        "match_rate_pct": round(len(used_b) / len(b) * 100, 1) if len(b) else 0.0,
        "by_tier": matches["tier"].value_counts().to_dict(),
        "needs_review": int(matches["needs_review"].sum()),
        "unmatched_bank_total": round(float(ub["amount"].sum()), 2),
        "unmatched_gl_total": round(float(ug["amount"].sum()), 2),
    }
    if bank_ending_balance is not None and gl_ending_balance is not None:
        # Adjusted balance proof: bank + GL-only items - bank-only items == GL.
        adjusted = bank_ending_balance + summary["unmatched_gl_total"] - summary["unmatched_bank_total"]
        summary["adjusted_bank_balance"] = round(adjusted, 2)
        summary["unexplained_difference"] = round(gl_ending_balance - adjusted, 2)
        summary["reconciled"] = abs(summary["unexplained_difference"]) <= amount_tol
    return ReconResult(matches=matches, unmatched_bank=ub, unmatched_gl=ug, summary=summary)
