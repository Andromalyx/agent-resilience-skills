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
    "currency",
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
                     "doituong", "đốitượng", "partner", "tendoituong", "madoituong"),
    "currency": ("currency", "ccy", "cur", "currencycode", "loaitien", "mant", "waers"),
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
    errors: list[str] = field(default_factory=list)  # blocking: numbers are unreliable
    dropped_rows: int = 0
    header_row: int = 0  # number of title rows skipped above the real header
    dayfirst: bool | None = None
    decimal: str = "."


def infer_decimal(series: pd.Series) -> str | None:
    """Infer the decimal separator for a text column ('.' or ',').

    Evidence for ',' decimal: ``1.234,56``, ``1.234.567`` (repeated dots = thousands),
    ``12,5``. Evidence for '.': ``1,234.56``, ``1,234,567``, ``12.5``.
    Returns None when the column carries no evidence (e.g. integers only).
    """
    if pd.api.types.is_numeric_dtype(series):
        return None
    text = series.dropna().astype(str).str.replace(r"[^\d,.]", "", regex=True)
    comma = (text.str.contains(r"\.\d{3}\.") | text.str.contains(r"\.\d{3},\d+$")
             | text.str.fullmatch(r"\d+,\d{1,2}") | text.str.fullmatch(r"\d{1,3}(\.\d{3})+")).sum()
    dot = (text.str.contains(r",\d{3},") | text.str.contains(r",\d{3}\.\d+$")
           | text.str.fullmatch(r"\d+\.\d{1,2}") | text.str.fullmatch(r"\d{1,3}(,\d{3})+")).sum()
    if comma == dot:
        return None if comma == 0 else "."
    return "," if comma > dot else "."


def parse_amount(series: pd.Series, decimal: str | None = None) -> pd.Series:
    """Parse accounting-formatted numbers; unparseable values become NaN (never 0).

    Handles ``1,234.56``, ``1.234,56``, ``1.200.000.000`` (VND), ``(1,234.56)``
    negatives, trailing minus ``1234-``, currency symbols, and blanks (-> 0).
    ``decimal``: '.' or ','; inferred per column when None (see ``infer_decimal``).
    """
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float).fillna(0.0)
    decimal = decimal or infer_decimal(series) or "."
    thousands = "," if decimal == "." else "."

    def _one(raw: object) -> float:
        if raw is None or (isinstance(raw, float) and np.isnan(raw)):
            return 0.0
        if isinstance(raw, (int, float, np.number)):
            return float(raw)
        text = str(raw).strip()
        if text in {"", "-", "—", "nan", "None"}:
            return 0.0
        negative = (text.startswith("(") and text.endswith(")")) or text.endswith("-") \
            or text.startswith("-")
        text = re.sub(r"[^\d,.]", "", text).replace(thousands, "").replace(decimal, ".")
        try:
            value = float(text) if text else 0.0
        except ValueError:
            return np.nan
        return -value if negative else value

    return series.map(_one).astype(float)


_DMY = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")


def infer_dayfirst(series: pd.Series) -> bool | None:
    """True = dd/mm, False = mm/dd, None = no slash-style dates or ambiguous."""
    text = series.dropna().astype(str)
    parts = text.str.extract(_DMY)
    if parts.dropna().empty:
        return None
    a, b = parts[0].dropna().astype(int), parts[1].dropna().astype(int)
    if (a > 12).any() and not (b > 12).any():
        return True
    if (b > 12).any() and not (a > 12).any():
        return False
    return None


def parse_dates(series: pd.Series, dayfirst: bool | None = None) -> tuple[pd.Series, str | None]:
    """Parse dates with explicit day/month order. Returns (dates, warning or None)."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series, None
    has_slash = series.dropna().astype(str).str.match(_DMY).any()
    warning = None
    if has_slash and dayfirst is None:
        dayfirst = infer_dayfirst(series)
        if dayfirst is None:
            dayfirst = False
            warning = ("Date order is ambiguous (no day > 12 found); assumed month/day. "
                       "Set dayfirst=True (or date_order: dmy in fpa-context) if dd/mm.")
    # Excel cells may already be datetime objects mixed with strings.
    out = series.map(lambda v: v if isinstance(v, (pd.Timestamp, np.datetime64)) or
                     hasattr(v, "year") else pd.to_datetime(v, errors="coerce",
                                                             dayfirst=bool(dayfirst)))
    return pd.to_datetime(out, errors="coerce"), warning


def _promote_header(raw: pd.DataFrame, max_scan: int = 30) -> tuple[pd.DataFrame, int]:
    """Find the real header row when exports have title lines above it.

    Picks the first row (within ``max_scan``) that maps an account column and >= 2
    other canonical columns. Returns (frame, header_row_index) - 0 means unchanged.
    """
    def _score(cells: list) -> tuple[bool, int]:
        canon = {_LOOKUP.get(_norm_header(c)) for c in cells if str(c).strip()}
        canon.discard(None)
        return "account" in canon, len(canon)

    has_acct, n = _score(list(raw.columns))
    if has_acct and n >= 3:
        return raw, 0
    for i in range(min(max_scan, len(raw))):
        has_acct, n = _score(raw.iloc[i].tolist())
        if has_acct and n >= 3:
            body = raw.iloc[i + 1:].copy()
            body.columns = [str(c).strip() for c in raw.iloc[i].tolist()]
            return body.reset_index(drop=True), i + 1
    return raw, 0


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
    if suffix in {".csv", ".txt", ".tsv"} and path.stat().st_size > 50_000_000:
        logger.info("Large CSV (%d MB); consider Parquet for speed", path.stat().st_size >> 20)
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
    dayfirst: bool | None = None,
    decimal: str | None = None,
) -> tuple[pd.DataFrame, LoadReport]:
    """Load G/L detail or a trial balance into the canonical frame.

    Args:
        source: path (.csv/.xlsx/.parquet) or DataFrame.
        column_map: optional ``{canonical: source_column}`` overrides.
        sheet: Excel sheet name/index.
        amount_sign: meaning of a single signed ``amount`` column. ``net_debit`` (debits
            positive - most ERPs) or ``natural`` (revenue positive, expenses positive -
            common in budget files; requires CoA to re-sign, see ``natural_to_net_debit``).
        dayfirst: date order for dd/mm vs mm/dd strings; inferred when None.
        decimal: '.' or ','; inferred per amount column when None.

    Returns:
        ``(frame, report)``. Rows with no account are dropped and counted.
    """
    raw = _read_any(source, sheet)
    report = LoadReport(source=str(source) if not isinstance(source, pd.DataFrame) else "<frame>")
    raw.columns = [str(c).strip() for c in raw.columns]
    if not column_map:
        raw, report.header_row = _promote_header(raw)
        if report.header_row:
            report.warnings.append(f"Skipped {report.header_row} title row(s) above the header.")
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

    amount_cols = [mapping[c] for c in ("debit", "credit", "amount") if c in mapping]
    if decimal is None:
        votes = [v for v in (infer_decimal(raw[c]) for c in amount_cols) if v]
        decimal = "," if votes.count(",") > votes.count(".") else "."
        if votes.count(",") and votes.count("."):
            report.warnings.append("Amount columns disagree on decimal separator; used "
                                   f"{decimal!r}. Set decimal explicitly to be sure.")
    report.decimal = decimal
    if decimal == ",":
        report.warnings.append("Detected ',' as decimal separator ('.' = thousands).")

    if has_dc:
        out["debit"] = parse_amount(raw[mapping["debit"]], decimal) if "debit" in mapping else 0.0
        out["credit"] = (parse_amount(raw[mapping["credit"]], decimal)
                         if "credit" in mapping else 0.0)
        # Some exports put negative numbers in the debit column for credits; normalize.
        out["amount"] = out["debit"] - out["credit"]
        if "amount" in mapping:
            report.warnings.append(
                f"Both debit/credit and amount ({mapping['amount']!r}) present; used debit-credit."
            )
    else:
        signed = parse_amount(raw[mapping["amount"]], decimal)
        out["amount"] = signed
        if amount_sign == "natural":
            report.warnings.append(
                "Amounts are in natural sign; call natural_to_net_debit() after mapping."
            )
    bad_amounts = int(out["amount"].isna().sum())
    if bad_amounts:
        sample = raw.loc[out["amount"].isna(), amount_cols].head(3).to_dict("records")
        report.errors.append(f"{bad_amounts} amount value(s) could not be parsed "
                             f"(e.g. {sample}); totals exclude them - fix the source.")
        out["amount"] = out["amount"].fillna(0.0)
    out["debit"] = out["amount"].clip(lower=0)
    out["credit"] = (-out["amount"]).clip(lower=0)

    # Dates and periods.
    if "date" in mapping:
        out["date"], date_warning = parse_dates(raw[mapping["date"]], dayfirst)
        report.dayfirst = dayfirst if dayfirst is not None else infer_dayfirst(raw[mapping["date"]])
        if date_warning:
            report.warnings.append(date_warning)
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

    for col in ("entry_id", "description", "cost_center", "counterparty", "currency"):
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
    from .coa import is_income_line

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
