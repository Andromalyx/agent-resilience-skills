# FP&A AI Coverage Matrix

Benchmarks the `skills/fpa` + `runtime.finance` scope against the key uses of AI in
FP&A described by IBM ("AI in financial planning and analysis", IBM Think) and
related IBM Think pages, plus ideas adopted from open-source finance skill repos.

Status: **Covered** · **Partial** · **Out of scope** (deliberately not built).

## IBM key uses

| IBM use | Status | Where | Notes / gap |
|---|---|---|---|
| Predictive forecasting (patterns traditional models miss) | Covered | `forecast.auto_forecast`, `forecast_pnl`, `seasonality_index` | Backtest-selected method (naive / MA / trend / seasonal naive / Holt-Winters), empirical intervals. Upgrade path: statsforecast / Prophet for many series; exogenous drivers not yet modeled statistically |
| Baseline forecasts with consistent logic, automated overnight | Partial | CLI `--forecast N`, deterministic pipeline | Scheduling is left to the platform (cron / APScheduler / Airflow); no scheduler shipped |
| Driver-based / rolling forecasts | Covered | `forecast.DriverModel` | Units x price, headcount x cost, % of revenue, fixed + growth |
| Anomaly detection (unusual transactions) | Covered | `anomaly.risk_rank`, `transaction_flags`, `account_period_outliers`, `benford_first_digit`, optional IsolationForest | Ranked review queue with reasons; precision@k feedback loop documented, not automated |
| Variance analysis | Covered | `variance.compare_pnl`, `drill_down`, `price_volume_mix`, `commentary` | Budget, forecast, prior-period; GL evidence; PVM |
| What-if / scenario modeling | Covered | `scenarios.run_scenarios`, `sensitivity`, `breakeven_revenue` | Linked COGS, tornado, break-even. No Monte Carlo yet |
| Risk / early signs of financial stress | Partial | `kpis.kpi_alerts`, `revenue_concentration` (HHI), `runway_months`, working-capital KPIs | Credit / liquidity stress models (Altman-Z etc.) not built |
| Natural-language queries of financial data | Covered | `examples/finance/langgraph_fpa_agent.py` (7 tools) + `skills/fpa/SKILL.md` | Read-only tools; LLM narrates, pandas computes |
| Automated reporting / narrative | Covered | `pipeline.render_markdown`, `templates/monthly-pnl-pack.md` | Evidence-bound commentary, open-items list |
| Data integration & cleansing | Covered | `ledger.load_ledger`, `coa.ChartOfAccounts`, `validation` | CSV/XLSX/Parquet, EN/VI headers, generic + VAS CoA. No live ERP connectors |
| Close acceleration / reconciliation | Covered | `reconcile.reconcile`, `references/gl-review-checks.md` | Tiered matching + balance proof |
| Sustainability (ESG) data in forecasts | Out of scope | - | Needs non-financial data sources; add when ESG data exists |
| Collaborative planning platforms | Out of scope | - | Product/platform concern (shared models, workflow, approvals) |
| Unstructured data (contracts, emails) | Out of scope | - | Possible future: contract-to-accrual extraction |

## Ideas adopted from reviewed repos

| Source | Idea | Adopted as |
|---|---|---|
| GAJETOso/financeskills (`ai-anomaly-detection`) | Composite score x materiality, precision@k, drift after org change | `risk_rank`, `references/anomaly-detection.md` |
| GAJETOso/financeskills (`forensic-accounting`) | Benford first digit + chi-square, round-number ratio | `benford_first_digit` (added Nigrini MAD + sample-size guard) |
| GAJETOso/financeskills (`automated-reconciliation`) | Tiered matching, noise-token normalization, one-to-many, log tier+score | `reconcile`, `references/reconciliation.md` |
| GAJETOso/financeskills (`evals/evals.json`) | Prompt + files + assertions eval format | `skills/fpa/evals/evals.json` + `tests/test_fpa_evals.py` |
| GAJETOso/financeskills ("import functions instead of mental math") | Deterministic scripts | Already the design principle of `runtime.finance` |
| openaccountant/skills (`revenue-concentration`) | HHI with 1,500 / 2,500 thresholds, > 25% key-client flag | `revenue_concentration` |
| openaccountant/skills (`seasonal-patterns`) | Month index (100 = avg), range > 50 pts = seasonal | `seasonality_index` |
| openaccountant/skills (`cash-flow-forecast`, `runway-calculator`) | Moving average baseline, runway | `moving_average` method, `runway_months` |
| Genzeldy/fpna-automation-engine | Rule-based insight thresholds (margin, marketing ratio, growth) | `kpi_alerts` with configurable thresholds |

## Not adopted (and why)

- Fixed growth-rate forecasts (Genzeldy: revenue x 1.05/month) - replaced by backtested
  methods; fixed growth is available explicitly via `DriverModel("fixed", amount, growth)`.
- Sending raw metrics to an LLM for "insights" without evidence - conflicts with the
  evidence-bound commentary rule.
- Personal-finance and tax skills (openaccountant) - outside the G/L / FP&A scope.
- Valuation, LBO, WACC, IFRS 9/16/17 computations (GAJETOso) - corporate finance /
  technical accounting, candidates for separate skills.
