# Changelog

All notable changes to this project will be documented in this file.

## 0.2.0

Readiness for real data in Claude Code (findings from an install-and-break audit):

- Fixed silent data corruption on real exports: dd/mm dates are inferred (and reported)
  instead of parsed as mm/dd; `1.200.000.000`-style VND amounts parse correctly instead
  of becoming 0; unparseable amounts are blocking errors, never silent zeros; title rows
  above the header are skipped.
- Closing entries (VAS 911 by default) are excluded so P&L balances are not zeroed; YTD
  trial balances are detected (`possible_cumulative_tb`) and converted with `--ytd`;
  mixed-currency ledgers are blocked.
- Company knowledge base `fpa-context/` (company.yaml, coa_map.csv, drivers.csv,
  notes.md) with `init-context` and `record-driver` (confirmed-by required); confirmed
  drivers and owners flow into commentary.
- Self-contained skill: engine vendored into `skills/fpa/scripts/fpa_engine` with an
  `fpa.py` launcher (`doctor`, `analyze`, `init-context`, `record-driver`, `reconcile`);
  sync script + drift test.
- Claude Code plugin + marketplace manifests (`claude plugin validate` passes); resilience
  skill gained frontmatter.
- CLI JSON now carries P&L, variance, evidence, queue, forecast, settings.
- 2.4x faster anomaly screen (vectorized); `docs/claude-code-setup.md`.

## Unreleased (0.1.x)

- Added `skills/fpa` (FP&A & G/L Analyst) skill: references for P&L structure, CoA mapping
  (generic + Vietnam VAS Circular 200), variance/flux analysis, G/L review checks, KPIs and
  forecasting; templates for variance commentary, monthly P&L pack, data requests.
- Added `runtime.finance` (pandas): ledger loader (EN/VI headers, accounting number
  formats), CoA mapper with mapping provenance, validation checks, P&L builder, variance
  engine, G/L drill-down, price-volume-mix, KPIs, evidence-bound commentary, CLI.
- Added finance pressure signals (plugging, earnings smoothing, backdating, unbalanced TB)
  to the resilience detector and `evals/datasets/finance_pressure_cases.jsonl`.
- Added sample G/L + budget and a LangGraph agent example under `examples/finance/`.
- Added `runtime.finance.forecast` (backtested auto-forecast incl. Holt-Winters, empirical
  intervals, seasonality index, `DriverModel`), `anomaly` (ranked review queue, robust z,
  Benford with Nigrini MAD, optional IsolationForest), `scenarios` (what-if, tornado,
  break-even), `reconcile` (tiered bank-to-GL matching + balance proof), revenue
  concentration (HHI), runway, KPI alerts; CLI `--forecast`, `--top-k`, `--no-anomalies`.
- Added `skills/fpa/evals/evals.json`, references for anomaly detection and
  reconciliation, `docs/fpa-ai-coverage.md`, and a 27-month seasonal sample G/L.

## 0.1.0 - Unreleased

- Initial repository scaffold.
- Added canonical resilience skill and adapter docs.
- Added lightweight Python runtime helpers.
- Added starter tests, eval datasets, rubrics, and examples.
