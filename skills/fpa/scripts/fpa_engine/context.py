"""Company knowledge base ("fpa-context") for real-data work.

A folder the agent reads before every analysis and appends to as facts get confirmed,
so knowledge about *your* books accumulates instead of being re-asked each session::

    fpa-context/
      company.yaml     settings: currency, CoA scheme, date/decimal format, materiality,
                       closing accounts, fiscal year, alert thresholds, owners, whitelist
      coa_map.csv      account,line            explicit CoA mapping (beats ranges/keywords)
      drivers.csv      period,line,driver,confirmed_by,confirmed_on
                       owner-confirmed variance explanations -> used in commentary
      notes.md         free-text business context (seasonality, events, policies)

Nothing here is required; every missing piece falls back to safe defaults, and the
report says which defaults were used.
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .coa import ALL_LINES, PNL_LINES, load_mapping_file

logger = logging.getLogger(__name__)

DRIVER_FIELDS = ["period", "line", "driver", "confirmed_by", "confirmed_on"]


@dataclass
class FinanceContext:
    root: Path | None = None
    company: str = ""
    functional_currency: str = ""
    scheme: str = "generic"
    fiscal_year_start_month: int = 1
    dayfirst: bool | None = None          # date_order: dmy -> True, mdy -> False, auto -> None
    decimal: str | None = None            # "." | "," | None (auto)
    materiality_abs: float = 10_000
    materiality_pct: float = 10.0
    materiality_rule: str = "and"
    closing_accounts: tuple[str, ...] | None = None  # None -> scheme default
    expect_balanced: bool = True
    cumulative_tb: bool | None = None     # None -> detect
    alert_thresholds: dict | None = None
    owners: dict[str, str] = field(default_factory=dict)
    whitelist_counterparties: tuple[str, ...] = ()
    coa_map: dict[str, str] = field(default_factory=dict)
    drivers: dict[tuple[str, str], str] = field(default_factory=dict)
    notes: str = ""
    sources: list[str] = field(default_factory=list)  # which files were loaded

    def owner_for(self, line: str) -> str:
        return self.owners.get(line, "budget owner")


def load_context(path: str | Path | None) -> FinanceContext:
    """Load ``fpa-context`` from a folder (missing folder/files -> defaults)."""
    ctx = FinanceContext()
    if path is None:
        return ctx
    root = Path(path).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"fpa-context folder not found: {root}")
    ctx.root = root

    cfg_path = root / "company.yaml"
    if cfg_path.exists():
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError("pip install pyyaml to read company.yaml") from exc
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        _apply_config(ctx, cfg)
        ctx.sources.append(cfg_path.name)

    if (root / "coa_map.csv").exists():
        ctx.coa_map = load_mapping_file(root / "coa_map.csv")
        ctx.sources.append("coa_map.csv")
    if (root / "drivers.csv").exists():
        with (root / "drivers.csv").open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("period") and row.get("line") and row.get("driver"):
                    who = row.get("confirmed_by") or "unconfirmed"
                    ctx.drivers[(row["period"].strip(), row["line"].strip())] = (
                        f"{row['driver'].strip()} (confirmed by {who})")
        ctx.sources.append("drivers.csv")
    if (root / "notes.md").exists():
        ctx.notes = (root / "notes.md").read_text(encoding="utf-8")
        ctx.sources.append("notes.md")
    return ctx


def _apply_config(ctx: FinanceContext, cfg: dict) -> None:
    ctx.company = str(cfg.get("company", ""))
    ctx.functional_currency = str(cfg.get("functional_currency", "")).upper()
    ctx.scheme = cfg.get("scheme", ctx.scheme)
    ctx.fiscal_year_start_month = int(cfg.get("fiscal_year_start_month", 1))
    order = str(cfg.get("date_order", "auto")).lower()
    if order not in {"auto", "dmy", "mdy", "ymd"}:
        raise ValueError(f"date_order must be auto|dmy|mdy|ymd, got {order!r}")
    ctx.dayfirst = {"dmy": True, "mdy": False}.get(order)
    dec = str(cfg.get("decimal", "auto"))
    if dec not in {"auto", ".", ","}:
        raise ValueError(f"decimal must be auto|.|, got {dec!r}")
    ctx.decimal = None if dec == "auto" else dec
    mat = cfg.get("materiality", {}) or {}
    ctx.materiality_abs = float(mat.get("abs", ctx.materiality_abs))
    ctx.materiality_pct = float(mat.get("pct", ctx.materiality_pct))
    ctx.materiality_rule = mat.get("rule", ctx.materiality_rule)
    if ctx.materiality_rule not in {"and", "or"}:
        raise ValueError("materiality.rule must be 'and' or 'or'")
    if "closing_accounts" in cfg:
        ctx.closing_accounts = tuple(str(a) for a in cfg["closing_accounts"] or ())
    ctx.expect_balanced = bool(cfg.get("expect_balanced", True))
    if "cumulative_tb" in cfg:
        ctx.cumulative_tb = cfg["cumulative_tb"]
    if cfg.get("alert_thresholds"):
        ctx.alert_thresholds = {k: tuple(v) for k, v in cfg["alert_thresholds"].items()}
    owners = cfg.get("owners", {}) or {}
    bad = sorted(set(owners) - set(PNL_LINES))
    if bad:
        raise ValueError(f"owners has unknown P&L lines {bad}; valid: {sorted(PNL_LINES)}")
    ctx.owners = {k: str(v) for k, v in owners.items()}
    ctx.whitelist_counterparties = tuple(cfg.get("anomaly_whitelist_counterparties", []) or [])


def record_driver(root: str | Path, period: str, line: str, driver: str,
                  confirmed_by: str) -> Path:
    """Append an owner-confirmed driver to ``drivers.csv`` (the agent's memory write).

    Only call after a person has stated or approved the explanation.
    """
    if line not in ALL_LINES:
        raise ValueError(f"Unknown line {line!r}")
    if not confirmed_by.strip():
        raise ValueError("confirmed_by is required - drivers must come from a person")
    path = Path(root) / "drivers.csv"
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=DRIVER_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"period": period, "line": line, "driver": driver,
                    "confirmed_by": confirmed_by, "confirmed_on": dt.datetime.now(dt.timezone.utc).date().isoformat()})
    return path
