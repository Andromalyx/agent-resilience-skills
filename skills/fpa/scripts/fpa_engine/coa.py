"""Chart-of-accounts (CoA) classification.

Maps raw G/L account numbers and names to standard P&L / balance-sheet lines.

Resolution order (first hit wins), and every result records *how* it was mapped
so the agent can disclose low-confidence mappings instead of presenting them as fact:

1. ``explicit``  - user-supplied mapping (CSV/dict). Always preferred.
2. ``range``     - numeric account ranges for a known scheme (``generic`` or ``vas``).
3. ``keyword``   - account-name keywords (EN + VI).
4. ``unmapped``  - nothing matched; excluded from P&L totals and reported.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# Standard lines
# --------------------------------------------------------------------------------------

#: P&L lines in presentation order. ``sign`` = +1 means credit-normal (income),
#: -1 means debit-normal (expense). Used for presentation and favorable/unfavorable.
PNL_LINES: dict[str, dict[str, object]] = {
    "revenue": {"label": "Revenue", "income": True},
    "contra_revenue": {"label": "Discounts, returns & allowances", "income": True},
    "cogs": {"label": "Cost of goods sold", "income": False},
    "opex_personnel": {"label": "Personnel / payroll", "income": False},
    "opex_sales_marketing": {"label": "Sales & marketing", "income": False},
    "opex_rnd": {"label": "Research & development", "income": False},
    "opex_facilities": {"label": "Rent & facilities", "income": False},
    "opex_ga": {"label": "General & administrative", "income": False},
    "depreciation_amortization": {"label": "Depreciation & amortization", "income": False},
    "other_income": {"label": "Other / financial income", "income": True},
    "interest_expense": {"label": "Interest & financial expense", "income": False},
    "other_expense": {"label": "Other expense", "income": False},
    "income_tax": {"label": "Income tax", "income": False},
}

BALANCE_SHEET_LINES = ("asset", "liability", "equity")

OPEX_LINES = (
    "opex_personnel",
    "opex_sales_marketing",
    "opex_rnd",
    "opex_facilities",
    "opex_ga",
)

ALL_LINES = tuple(PNL_LINES) + BALANCE_SHEET_LINES


def is_income_line(line: str) -> bool:
    """True for credit-normal P&L lines (revenue, other income)."""
    return bool(PNL_LINES.get(line, {}).get("income", False))


# --------------------------------------------------------------------------------------
# Range schemes. Ranges are matched on the account's leading digits.
# --------------------------------------------------------------------------------------

# (prefix_start, prefix_end, line) – inclusive, compared on the first N digits where
# N = len(prefix_start). Ordered from most to least specific.
_GENERIC_RANGES: tuple[tuple[str, str, str], ...] = (
    ("1", "1", "asset"),
    ("2", "2", "liability"),
    ("3", "3", "equity"),
    ("49", "49", "contra_revenue"),
    ("4", "4", "revenue"),
    ("5", "5", "cogs"),
    ("60", "61", "opex_personnel"),
    ("62", "63", "opex_sales_marketing"),
    ("64", "64", "opex_rnd"),
    ("65", "65", "opex_facilities"),
    ("68", "68", "depreciation_amortization"),
    ("66", "67", "opex_ga"),
    ("69", "69", "opex_ga"),
    ("7", "7", "opex_ga"),
    ("80", "80", "other_income"),
    ("81", "82", "interest_expense"),
    ("83", "89", "other_expense"),
    ("9", "9", "income_tax"),
)

# Vietnamese Accounting Standards (Circular 200/2014/TT-BTC, Circular 133 compatible).
_VAS_RANGES: tuple[tuple[str, str, str], ...] = (
    ("1", "2", "asset"),          # 1xx current, 2xx non-current assets (214 handled below)
    ("3", "3", "liability"),
    ("4", "4", "equity"),
    ("521", "521", "contra_revenue"),
    ("511", "512", "revenue"),
    ("515", "515", "other_income"),  # financial income
    ("632", "632", "cogs"),
    ("635", "635", "interest_expense"),  # financial expense
    ("6411", "6411", "opex_personnel"),
    ("6421", "6421", "opex_personnel"),
    ("6414", "6414", "depreciation_amortization"),
    ("6424", "6424", "depreciation_amortization"),
    ("641", "641", "opex_sales_marketing"),
    ("642", "642", "opex_ga"),
    ("711", "711", "other_income"),
    ("811", "811", "other_expense"),
    ("821", "821", "income_tax"),
    # 9xx (911 P&L closing) and 0xx (off-balance) intentionally unmapped.
)

SCHEMES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "generic": _GENERIC_RANGES,
    "vas": _VAS_RANGES,
}

# --------------------------------------------------------------------------------------
# Keyword fallback (lowercase, EN + VI). Checked in order; first hit wins.
# --------------------------------------------------------------------------------------

_KEYWORDS: tuple[tuple[str, str], ...] = (
    (r"discount|return|allowance|rebate|giảm trừ|chiết khấu", "contra_revenue"),
    (r"depreciation|amortization|amortisation|khấu hao", "depreciation_amortization"),
    (r"income tax|corporate tax|thuế tndn|thuế thu nhập doanh nghiệp", "income_tax"),
    (r"interest expense|bank charge|fx loss|chi phí tài chính|lãi vay", "interest_expense"),
    (r"interest income|fx gain|doanh thu tài chính|other income|thu nhập khác", "other_income"),
    (r"cost of (goods|sales|revenue)|cogs|giá vốn", "cogs"),
    (r"revenue|sales|doanh thu", "revenue"),
    (r"salary|salaries|wage|payroll|bonus|benefit|lương|bảo hiểm", "opex_personnel"),
    (r"marketing|advertis|promotion|commission|quảng cáo|bán hàng", "opex_sales_marketing"),
    (r"research|development|r&d", "opex_rnd"),
    (r"rent|lease|utilit|facilit|thuê|điện|nước", "opex_facilities"),
    (r"office|admin|legal|audit|insurance|software|travel|quản lý", "opex_ga"),
    (r"other expense|chi phí khác|penalt", "other_expense"),
)


@dataclass(frozen=True)
class AccountMapping:
    """Mapping result for one account."""

    account: str
    account_name: str
    line: str | None
    source: str  # explicit | range | keyword | unmapped

    @property
    def is_pnl(self) -> bool:
        return self.line in PNL_LINES


def _digits(account: str) -> str:
    """Leading digits of an account code (strips separators like '6100-01' -> '610001')."""
    return re.sub(r"\D", "", str(account))


def _match_range(account: str, scheme: str) -> str | None:
    digits = _digits(account)
    if not digits:
        return None
    for start, end, line in SCHEMES[scheme]:
        width = len(start)
        prefix = digits[:width]
        if len(prefix) == width and start <= prefix <= end:
            # VAS: 214 (accumulated depreciation) is a contra-asset, still a BS line.
            return line
    return None


def _match_keyword(name: str) -> str | None:
    lowered = (name or "").lower()
    for pattern, line in _KEYWORDS:
        if re.search(pattern, lowered):
            return line
    return None


def load_mapping_file(path: str | Path) -> dict[str, str]:
    """Load an explicit mapping CSV with columns ``account,line``.

    Raises ``ValueError`` for unknown line names so typos fail loudly.
    """
    df = pd.read_csv(path, dtype=str)
    missing = {"account", "line"} - set(df.columns.str.lower())
    if missing:
        raise ValueError(f"Mapping file {path} missing columns: {sorted(missing)}")
    df.columns = df.columns.str.lower()
    bad = sorted(set(df["line"]) - set(ALL_LINES))
    if bad:
        raise ValueError(f"Unknown line names in mapping file: {bad}. Valid: {ALL_LINES}")
    return dict(zip(df["account"].str.strip(), df["line"].str.strip()))


class ChartOfAccounts:
    """Classify accounts into standard lines with provenance."""

    def __init__(
        self,
        scheme: str = "generic",
        explicit: Mapping[str, str] | None = None,
        use_keywords: bool = True,
    ) -> None:
        if scheme not in SCHEMES:
            raise ValueError(f"Unknown scheme {scheme!r}. Choose from {sorted(SCHEMES)}")
        self.scheme = scheme
        self.explicit = {str(k).strip(): v for k, v in (explicit or {}).items()}
        self.use_keywords = use_keywords

    def classify(self, account: str, account_name: str = "") -> AccountMapping:
        """Classify a single account."""
        account = str(account).strip()
        if account in self.explicit:
            return AccountMapping(account, account_name, self.explicit[account], "explicit")
        line = _match_range(account, self.scheme)
        if line:
            return AccountMapping(account, account_name, line, "range")
        if self.use_keywords:
            line = _match_keyword(account_name)
            if line:
                return AccountMapping(account, account_name, line, "keyword")
        return AccountMapping(account, account_name, None, "unmapped")

    def classify_frame(self, accounts: pd.DataFrame | Iterable[tuple[str, str]]) -> pd.DataFrame:
        """Classify unique ``(account, account_name)`` pairs.

        Returns a DataFrame with columns ``account, account_name, line, source``.
        """
        if isinstance(accounts, pd.DataFrame):
            pairs = (
                accounts[["account", "account_name"]]
                .drop_duplicates("account")
                .itertuples(index=False, name=None)
            )
        else:
            pairs = accounts
        rows = [self.classify(a, n).__dict__ for a, n in pairs]
        result = pd.DataFrame(rows, columns=["account", "account_name", "line", "source"])
        unmapped = int((result["source"] == "unmapped").sum())
        if unmapped:
            logger.warning("%d account(s) could not be mapped", unmapped)
        return result
