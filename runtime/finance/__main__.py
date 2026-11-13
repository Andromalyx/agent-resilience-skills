"""FP&A engine CLI.

Subcommands (``analyze`` is the default when the first argument is an option)::

    analyze        --gl FILE [--budget FILE] [--context DIR] [--period YYYY-MM] ...
    init-context   DIR [--scheme vas] [--currency VND]   create an fpa-context skeleton
    record-driver  DIR --period P --line L --driver TEXT --confirmed-by NAME
    reconcile      --bank FILE --gl FILE [--bank-balance X --gl-balance Y]
    doctor                                               check dependencies

Exit codes (analyze/reconcile): 0 ok, 2 warnings / unmatched items, 3 blocking
data-quality errors, 4 bad input or missing dependency.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

import pandas as pd

TEMPLATE_DIR = Path(__file__).resolve().parent / "context_template"


def _df_records(df: pd.DataFrame | None, max_rows: int = 200) -> list[dict]:
    if df is None:
        return []
    out = df.head(max_rows).copy()
    for col in out.select_dtypes(include=["datetime", "datetimetz"]).columns:
        out[col] = out[col].dt.strftime("%Y-%m-%d")
    return json.loads(out.reset_index().to_json(orient="records", default_handler=str))


# ------------------------------------------------------------------ analyze


def _analyze(argv: list[str]) -> int:
    from .pipeline import analyze

    p = argparse.ArgumentParser(prog="fpa analyze", description="P&L review of a G/L or TB")
    p.add_argument("--gl", required=True, help="G/L detail or trial balance (.csv/.xlsx/.parquet)")
    p.add_argument("--budget", help="Budget/forecast file (account, period, amount)")
    p.add_argument("--context", help="fpa-context folder (company knowledge base)")
    p.add_argument("--period", help="YYYY-MM to review (default: latest)")
    p.add_argument("--scheme", choices=["generic", "vas"], help="CoA scheme (default: context)")
    p.add_argument("--mapping", help="CSV account,line overrides (added to context coa_map)")
    p.add_argument("--materiality-abs", type=float)
    p.add_argument("--materiality-pct", type=float)
    p.add_argument("--pnl-only", action="store_true",
                   help="Extract has only P&L accounts; don't require TB to balance")
    p.add_argument("--ytd", action="store_true", help="Input is a YTD (cumulative) TB")
    order = p.add_mutually_exclusive_group()
    order.add_argument("--dayfirst", action="store_true", help="Dates are dd/mm/yyyy")
    order.add_argument("--monthfirst", action="store_true", help="Dates are mm/dd/yyyy")
    p.add_argument("--decimal", choices=[".", ","], help="Decimal separator (default: infer)")
    p.add_argument("--closing-accounts", help="Comma list, e.g. 911 or 3999")
    p.add_argument("--drill-by", default="counterparty",
                   choices=["counterparty", "description", "cost_center", "account"])
    p.add_argument("--forecast", type=int, default=0, metavar="N",
                   help="Add an N-period statistical forecast")
    p.add_argument("--no-anomalies", action="store_true", help="Skip anomaly screen")
    p.add_argument("--top-k", type=int, default=15, help="Rows in the review queue")
    p.add_argument("--out", help="Write markdown report to this path")
    p.add_argument("--json", action="store_true", help="Print full JSON result to stdout")
    p.add_argument("--json-out", help="Write full JSON result to this path")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        r = analyze(
            a.gl, period=a.period, budget=a.budget, scheme=a.scheme, mapping_file=a.mapping,
            materiality_abs=a.materiality_abs, materiality_pct=a.materiality_pct,
            expect_balanced=False if a.pnl_only else None, drill_by=a.drill_by,
            forecast_horizon=a.forecast, anomalies=not a.no_anomalies, top_k=a.top_k,
            context=a.context, cumulative=True if a.ytd else None,
            dayfirst=True if a.dayfirst else (False if a.monthfirst else None),
            decimal=a.decimal,
            closing_accounts=a.closing_accounts.split(",") if a.closing_accounts else None,
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4

    md = r.to_markdown()
    payload = {
        "period": r.period, "baseline": r.baseline_name, "baseline_period": r.baseline_period,
        "confidence": r.confidence, "settings": r.settings,
        "load": {"rows": r.load_report.rows, "column_map": r.load_report.column_map,
                 "warnings": r.load_report.warnings, "errors": r.load_report.errors},
        "findings": r.validation.to_frame().to_dict("records"),
        "pnl": _df_records(r.pnl),
        "variance": _df_records(r.variance),
        "evidence": {k: _df_records(v) for k, v in r.evidence.items()},
        "commentary": r.commentary, "kpis": r.kpis, "alerts": r.alerts,
        "concentration": {**(r.concentration.attrs if r.concentration is not None else {}),
                          "rows": _df_records(r.concentration)},
        "review_queue": _df_records(r.review_queue),
        "account_outliers": _df_records(r.account_outliers),
        "forecast": _df_records(r.forecast),
        "unmapped_accounts": r.mapping.loc[r.mapping["source"] == "unmapped",
                                           ["account", "account_name"]].to_dict("records"),
    }
    text = json.dumps(payload, indent=2, default=str)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"wrote {a.out}", file=sys.stderr)
    if a.json_out:
        Path(a.json_out).write_text(text, encoding="utf-8")
        print(f"wrote {a.json_out}", file=sys.stderr)
    if a.json:
        print(text)
    elif not a.out and not a.json_out:
        print(md)
    if not r.validation.ok:
        return 3
    return 2 if any(f.severity == "warning" for f in r.validation.findings) else 0


# ------------------------------------------------------------------ context


def _init_context(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="fpa init-context")
    p.add_argument("dir")
    p.add_argument("--scheme", default="generic", choices=["generic", "vas"])
    p.add_argument("--currency", default="")
    p.add_argument("--company", default="")
    a = p.parse_args(argv)
    root = Path(a.dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    created = []
    for src in sorted(TEMPLATE_DIR.iterdir()):
        dst = root / src.name
        if dst.exists():
            continue  # never overwrite existing knowledge
        shutil.copy(src, dst)
        created.append(src.name)
    cfg = root / "company.yaml"
    if "company.yaml" in created:
        text = cfg.read_text(encoding="utf-8")
        text = text.replace("scheme: generic", f"scheme: {a.scheme}")
        if a.scheme == "vas":
            text = text.replace("date_order: auto", "date_order: dmy").replace(
                "decimal: auto", 'decimal: ","').replace("closing_accounts: []",
                                                       'closing_accounts: ["911"]')
        if a.currency:
            text = text.replace('functional_currency: ""', f"functional_currency: {a.currency}")
        if a.company:
            text = text.replace('company: ""', f'company: "{a.company}"')
        cfg.write_text(text, encoding="utf-8")
    print(json.dumps({"context": str(root), "created": created,
                      "kept_existing": sorted({s.name for s in TEMPLATE_DIR.iterdir()}
                                              - set(created))}, indent=2))
    return 0


def _record_driver(argv: list[str]) -> int:
    from .context import record_driver

    p = argparse.ArgumentParser(prog="fpa record-driver",
                                description="Append an owner-confirmed variance driver")
    p.add_argument("dir")
    p.add_argument("--period", required=True)
    p.add_argument("--line", required=True)
    p.add_argument("--driver", required=True)
    p.add_argument("--confirmed-by", required=True)
    a = p.parse_args(argv)
    try:
        path = record_driver(a.dir, a.period, a.line, a.driver, a.confirmed_by)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    print(f"recorded in {path}")
    return 0


# ------------------------------------------------------------------ reconcile


def _reconcile(argv: list[str]) -> int:
    from .ledger import load_ledger
    from .reconcile import reconcile

    p = argparse.ArgumentParser(prog="fpa reconcile")
    p.add_argument("--bank", required=True, help="Bank statement: date, amount, [reference, description]")
    p.add_argument("--gl", required=True, help="GL cash lines (or full GL + --cash-account)")
    p.add_argument("--cash-account", help="Filter GL to this account (prefix)")
    p.add_argument("--bank-balance", type=float)
    p.add_argument("--gl-balance", type=float)
    p.add_argument("--review-threshold", type=float, default=1_000)
    p.add_argument("--json-out")
    a = p.parse_args(argv)
    try:
        bank = _bank_frame(a.bank)
        gl, _ = load_ledger(a.gl)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    if a.cash_account:
        gl = gl[gl["account"].str.startswith(a.cash_account)]
    gl = gl.rename(columns={"entry_id": "reference"})
    r = reconcile(bank, gl, review_threshold=a.review_threshold,
                  bank_ending_balance=a.bank_balance, gl_ending_balance=a.gl_balance)
    out = {"summary": r.summary, "matches": _df_records(r.matches, 500),
           "unmatched_bank": _df_records(r.unmatched_bank), "unmatched_gl": _df_records(r.unmatched_gl)}
    text = json.dumps(out, indent=2, default=str)
    if a.json_out:
        Path(a.json_out).write_text(text, encoding="utf-8")
    print(json.dumps(r.summary, indent=2, default=str) if a.json_out else text)
    if r.summary.get("reconciled") is False:
        return 3
    return 2 if len(r.unmatched_bank) or len(r.unmatched_gl) or r.summary["needs_review"] else 0


def _bank_frame(path: str) -> pd.DataFrame:
    """Bank statement -> date, amount (receipts +), reference, description."""
    from .ledger import _norm_header, parse_amount, parse_dates

    df = (pd.read_csv(path, dtype=str) if path.lower().endswith((".csv", ".txt"))
          else pd.read_excel(path, dtype=object))
    cols = {_norm_header(c): c for c in df.columns}

    def pick(*names: str) -> str | None:
        return next((cols[n] for n in names if n in cols), None)

    date_c = pick("date", "transactiondate", "valuedate", "postingdate", "ngay", "ngaygiaodich")
    if not date_c:
        raise ValueError(f"Bank file needs a date column: {list(df.columns)}")
    out = pd.DataFrame({"date": parse_dates(df[date_c])[0]})
    amt_c = pick("amount", "value", "sotien")
    if amt_c:
        out["amount"] = parse_amount(df[amt_c])
    else:
        dep = pick("deposit", "deposits", "credit", "moneyin", "ghico", "sotienghico")
        wd = pick("withdrawal", "withdrawals", "debit", "moneyout", "ghino", "sotienghino")
        if not dep or not wd:
            raise ValueError("Bank file needs an amount column or deposit + withdrawal columns")
        out["amount"] = parse_amount(df[dep]) - parse_amount(df[wd])
    ref = pick("reference", "ref", "checkno", "chequeno", "sothamchieu", "magiaodich")
    desc = pick("description", "memo", "details", "narrative", "noidung", "diengiai")
    out["reference"] = df[ref].fillna("").astype(str) if ref else ""
    out["description"] = df[desc].fillna("").astype(str) if desc else ""
    return out


# ------------------------------------------------------------------ doctor


def _doctor(argv: list[str]) -> int:
    import importlib

    report = {"python": sys.version.split()[0], "engine": str(Path(__file__).resolve().parent)}
    missing = []
    for mod, need in (("pandas", True), ("numpy", True), ("openpyxl", True), ("yaml", True),
                      ("sklearn", False), ("rapidfuzz", False)):
        try:
            m = importlib.import_module(mod)
            report[mod] = getattr(m, "__version__", "ok")
        except ImportError:
            report[mod] = "MISSING" + ("" if need else " (optional)")
            if need:
                missing.append({"yaml": "pyyaml", "sklearn": "scikit-learn"}.get(mod, mod))
    if missing:
        report["fix"] = f"pip install {' '.join(missing)}"
    print(json.dumps(report, indent=2))
    return 4 if missing else 0


COMMANDS = {"analyze": _analyze, "init-context": _init_context,
            "record-driver": _record_driver, "reconcile": _reconcile, "doctor": _doctor}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    if argv[0].startswith("-"):  # backward compatible: options only -> analyze
        return _analyze(argv)
    cmd = COMMANDS.get(argv[0])
    if cmd is None:
        print(f"unknown command {argv[0]!r}; choose from {sorted(COMMANDS)}", file=sys.stderr)
        return 4
    return cmd(argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
