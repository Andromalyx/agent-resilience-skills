# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

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
