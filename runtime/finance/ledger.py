"""Load and normalize G/L detail, trial balances, and budgets.

All loaders return a canonical frame so downstream code never guesses column names:

=============  ==========================================================
column         meaning
=============  ==========================================================
date           posting date (datetime64, NaT if source has periods only)
period         ``YYYY-MM`` string
account        account code (string, never float - preserves leading zeros)
account_name   account description (may be empty)
debit/credit   non-negative amounts
amount         signed **net debit** = debit - credit (expenses +, income -)
entry_id       journal entry id (optional)
description    line memo (optional)
cost_center    department / cost center (optional)
counterparty   vendor / customer (optional)
=============  ==========================================================
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CANONICAL_COLUMNS = (
    "date",
    "period",
    "account",
    "account_name",
    "debit",
    "credit",
    "amount",
    "entry_id",
    "description",
    "cost_center",
    "counterparty",
)

# Header synonyms (normalized: lowercase, non-alphanumerics stripped). EN + VI (no accents
# and with accents) so exports from QuickBooks, Xero, NetSuite, SAP, MISA, Fast work.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "date": ("date", "postingdate", "transdate", "transactiondate", "glDate", "ngay",
             "ngayhachtoan", "ngàyhạchtoán", "ngày", "documentdate", "docdate"),
    "period": ("period", "fiscalperiod", "month", "ky", "kỳ", "postingperiod", "yearmonth"),
    "account": ("account", "accountno", "accountnumber", "accountcode", "glaccount", "acct",
                "gl", "glcode", "taikhoan", "tàikhoản", "sotaikhoan", "tk", "hkont"),
    "account_name": ("accountname", "accountdescription", "glname", "accounttitle",
                     "tentaikhoan", "têntàikhoản"),
    "debit": ("debit", "dr", "debitamount", "nợ", "psno", "phatsinhno", "psnợ"),
    "credit": ("credit", "cr", "creditamount", "có", "psco", "phatsinhco", "pscó"),
    "amount": ("amount", "netamount", "balance", "value", "sotien", "sốtiền", "actual",
               "budget", "amountlc", "localamount"),
    "entry_id": ("entryid", "journalid", "je", "jeno", "journalno", "documentno", "docno",
                 "voucher", "voucherno", "sochungtu", "sốchứngtừ", "transactionid", "belnr"),
    "description": ("description", "memo", "narration", "linedescription", "text",
                    "diengiai", "diễngiải"),
    "cost_center": ("costcenter", "department", "dept", "class", "division", "bophan",
                    "bộphận", "kostl"),
    "counterparty": ("vendor", "customer", "counterparty", "name", "supplier", "payee",
                     "doituong", "đốitượng", "partner"),
}


def _norm_header(header: str) -> str:
    """Lowercase, strip accents (Vietnamese-safe: đ->d), drop non-alphanumerics."""
    text = unicodedata.normalize("NFD", str(header).lower().replace("đ", "d"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^0-9a-z]", "", text)


_LOOKUP = {_norm_header(s): canon for canon, syns in _SYNONYMS.items() for s in syns}


@dataclass
class LoadReport:
    """What the loader did - surfaced to the user so assumptions are explicit."""

    source: str
    rows: int = 0
    column_map: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    dropped_rows: int = 0


def parse_amount(series: pd.Series) -> pd.Series:
    """Parse accounting-formatted numbers.

    Handles ``1,234.56``, ``(1,234.56)`` negatives, trailing minus ``1234-``, currency
    symbols, and blanks. European ``1.234,56`` is detected when a comma is the last
    separator and followed by exactly two digits.
    """
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float).fillna(0.0)

    def _one(raw: object) -> float:
        if raw is None or (isinstance(raw, float) and np.isnan(raw)):
            return 0.0
        text = str(raw).strip()
        if text in {"", "-", "—"}:
            return 0.0
        negative = text.startswith("(") and text.endswith(")") or text.endswith("-")
        text = re.sub(r"[^\d,.\-]", "", text).strip("-")
        if re.search(r",\d{2}$", text) and "." in text:  # 1.234,56
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
        if text.startswith("-"):
            negative, text = True, text[1:]
        try:
            value = float(text) if text else 0.0
        except ValueError:
            return np.nan
        return -value if negative else value

    return series.map(_one).astype(float)


def _detect_columns(columns: list[str], overrides: Mapping[str, str] | None) -> dict[str, str]:
    """Return ``{canonical: source_column}``."""
    mapping: dict[str, str] = {}
    for canon, src in (overrides or {}).items():
        if src not in columns:
            raise KeyError(f"Override column {src!r} for {canon!r} not in file: {columns}")
        mapping[canon] = src
    for col in columns:
        canon = _LOOKUP.get(_norm_header(col))
        if canon and canon not in mapping and col not in mapping.values():
            mapping[canon] = col
    return mapping


def _read_any(source: str | Path | pd.DataFrame, sheet: str | int | None) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy()
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        # dtype=object keeps account codes like '0010' intact.
        return pd.read_excel(path, sheet_name=sheet or 0, dtype=object)
    if suffix in {".csv", ".txt", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else None
        return pd.read_csv(path, sep=sep, engine="python", dtype=str, encoding_errors="replace")
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def load_ledger(
    source: str | Path | pd.DataFrame,
    column_map: Mapping[str, str] | None = None,
    sheet: str | int | None = None,
    amount_sign: str = "net_debit",
) -> tuple[pd.DataFrame, LoadReport]:
    """Load G/L detail or a trial balance into the canonical frame.

    Args:
        source: path (.csv/.xlsx/.parquet) or DataFrame.
        column_map: optional ``{canonical: source_column}`` overrides.
        sheet: Excel sheet name/index.
        amount_sign: meaning of a single signed ``amount`` column. ``net_debit`` (debits
            positive - most ERPs) or ``natural`` (revenue positive, expenses positive -
            common in budget files; requires CoA to re-sign, see ``natural_to_net_debit``).

    Returns:
        ``(frame, report)``. Rows with no account are dropped and counted.
    """
    raw = _read_any(source, sheet)
    report = LoadReport(source=str(source) if not isinstance(source, pd.DataFrame) else "<frame>")
    raw.columns = [str(c).strip() for c in raw.columns]
    mapping = _detect_columns(list(raw.columns), column_map)
    report.column_map = dict(mapping)

    if "account" not in mapping:
        raise ValueError(
            f"Could not find an account column in {list(raw.columns)}. "
            "Pass column_map={'account': '<your column>'}."
        )
    has_dc = "debit" in mapping or "credit" in mapping
    if not has_dc and "amount" not in mapping:
        raise ValueError("Need debit/credit columns or a signed amount column.")

    out = pd.DataFrame(index=raw.index)
    out["account"] = (
        raw[mapping["account"]].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    )
    out["account_name"] = (
        raw[mapping["account_name"]].fillna("").astype(str).str.strip()
        if "account_name" in mapping
        else ""
    )

    if has_dc:
        out["debit"] = parse_amount(raw[mapping["debit"]]) if "debit" in mapping else 0.0
        out["credit"] = parse_amount(raw[mapping["credit"]]) if "credit" in mapping else 0.0
        # Some exports put negative numbers in the debit column for credits; normalize.
        out["amount"] = out["debit"] - out["credit"]
        if "amount" in mapping:
            report.warnings.append(
                f"Both debit/credit and amount ({mapping['amount']!r}) present; used debit-credit."
            )
    else:
        signed = parse_amount(raw[mapping["amount"]])
        out["amount"] = signed
        if amount_sign == "natural":
            report.warnings.append(
                "Amounts are in natural sign; call natural_to_net_debit() after mapping."
            )
    out["debit"] = out["amount"].clip(lower=0)
    out["credit"] = (-out["amount"]).clip(lower=0)

    bad_amounts = int(out["amount"].isna().sum())
    if bad_amounts:
        report.warnings.append(f"{bad_amounts} amount value(s) could not be parsed; set to 0.")
        out["amount"] = out["amount"].fillna(0.0)

    # Dates and periods.
    if "date" in mapping:
        out["date"] = pd.to_datetime(raw[mapping["date"]], errors="coerce", dayfirst=False)
        bad_dates = int(out["date"].isna().sum() - raw[mapping["date"]].isna().sum())
        if bad_dates > 0:
            report.warnings.append(f"{bad_dates} date value(s) could not be parsed.")
    else:
        out["date"] = pd.NaT
    if "period" in mapping:
        out["period"] = _normalize_period(raw[mapping["period"]])
    elif "date" in mapping:
        out["period"] = out["date"].dt.strftime("%Y-%m").fillna("UNKNOWN")
    else:
        out["period"] = "ALL"
        report.warnings.append("No date/period column; all rows treated as one period 'ALL'.")

    for col in ("entry_id", "description", "cost_center", "counterparty"):
        out[col] = raw[mapping[col]].fillna("").astype(str).str.strip() if col in mapping else ""

    # Drop rows with no account (subtotal/blank lines in exports).
    no_account = out["account"].isin({"", "nan", "None", "NaN"})
    report.dropped_rows = int(no_account.sum())
    if report.dropped_rows:
        report.warnings.append(f"Dropped {report.dropped_rows} row(s) with no account code.")
    out = out.loc[~no_account, list(CANONICAL_COLUMNS)].reset_index(drop=True)
    report.rows = len(out)
    logger.info("Loaded %d rows from %s", report.rows, report.source)
    return out, report


def _normalize_period(series: pd.Series) -> pd.Series:
    """Coerce 'Jul 2026', '2026-07', '07/2026', '202607', datetimes to 'YYYY-MM'."""

    def _one(value: object) -> str:
        text = str(value).strip()
        if re.fullmatch(r"\d{6}", text):
            return f"{text[:4]}-{text[4:]}"
        if m := re.fullmatch(r"(\d{1,2})[/\-.](\d{4})", text):
            return f"{m.group(2)}-{int(m.group(1)):02d}"
        if re.fullmatch(r"\d{4}-\d{2}", text):
            return text
        parsed = pd.to_datetime(text, errors="coerce")
        return parsed.strftime("%Y-%m") if not pd.isna(parsed) else text

    return series.map(_one)


def natural_to_net_debit(frame: pd.DataFrame, mapped: pd.DataFrame) -> pd.DataFrame:
    """Convert natural-sign amounts (income positive) to net-debit using account lines.

    ``mapped`` must have ``account`` and ``line`` columns (from ``ChartOfAccounts``).
    """
    from runtime.finance.coa import is_income_line

    lines = dict(zip(mapped["account"], mapped["line"]))
    credit_normal = {"liability", "equity"}
    # contra_revenue is debit-normal (a positive natural discount reduces revenue).
    flip = frame["account"].map(
        lambda a: (is_income_line(lines.get(a) or "") and lines.get(a) != "contra_revenue")
        or lines.get(a) in credit_normal
    )
    out = frame.copy()
    out.loc[flip, "amount"] = -out.loc[flip, "amount"]
    out["debit"] = out["amount"].clip(lower=0)
    out["credit"] = (-out["amount"]).clip(lower=0)
    return out
