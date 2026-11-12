"""CLI: ``python -m runtime.finance --gl gl.csv [--budget budget.csv] [--period 2026-09]``.

Exit codes: 0 ok, 2 completed with warnings, 3 blocking data-quality errors, 4 bad input.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from runtime.finance.pipeline import analyze


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runtime.finance", description=__doc__)
    parser.add_argument("--gl", required=True, help="G/L detail or trial balance (.csv/.xlsx)")
    parser.add_argument("--budget", help="Budget/forecast file (account, period, amount)")
    parser.add_argument("--period", help="YYYY-MM to review (default: latest)")
    parser.add_argument("--scheme", default="generic", choices=["generic", "vas"])
    parser.add_argument("--mapping", help="CSV account,line overrides")
    parser.add_argument("--materiality-abs", type=float, default=10_000)
    parser.add_argument("--materiality-pct", type=float, default=10.0)
    parser.add_argument("--pnl-only", action="store_true",
                        help="Extract has only P&L accounts; don't require TB to balance")
    parser.add_argument("--drill-by", default="counterparty",
                        choices=["counterparty", "description", "cost_center", "account"])
    parser.add_argument("--forecast", type=int, default=0, metavar="N",
                        help="Add an N-period statistical forecast")
    parser.add_argument("--no-anomalies", action="store_true", help="Skip anomaly screen")
    parser.add_argument("--top-k", type=int, default=15, help="Rows in the review queue")
    parser.add_argument("--out", help="Write markdown report to this path")
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    try:
        result = analyze(
            args.gl, period=args.period, budget=args.budget, scheme=args.scheme,
            mapping_file=args.mapping, materiality_abs=args.materiality_abs,
            materiality_pct=args.materiality_pct, expect_balanced=not args.pnl_only,
            drill_by=args.drill_by, forecast_horizon=args.forecast,
            anomalies=not args.no_anomalies, top_k=args.top_k,
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4

    md = result.to_markdown()
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    if args.json:
        print(json.dumps({
            "period": result.period,
            "baseline": result.baseline_name,
            "baseline_period": result.baseline_period,
            "confidence": result.confidence,
            "findings": result.validation.to_frame().to_dict("records"),
            "kpis": result.kpis,
            "alerts": result.alerts,
            "review_queue": (result.review_queue.to_dict("records")
                             if result.review_queue is not None else []),
            "commentary": result.commentary,
        }, indent=2, default=str))
    elif not args.out:
        print(md)

    if not result.validation.ok:
        return 3
    return 2 if any(f.severity == "warning" for f in result.validation.findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
