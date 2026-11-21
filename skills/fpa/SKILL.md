---
name: fpa-gl-analyst
description: Read and explain a company's financials from G/L detail, trial balances, P&L exports, bank statements and budgets, using a bundled offline engine and a per-company knowledge base (fpa-context). Use when the user shares or asks about a general ledger / sổ cái, trial balance, chart of accounts, P&L / income statement, budget vs actual, flux / variance analysis, month-end close, bank reconciliation, unusual transactions, forecast, what-if scenarios, margins, opex, EBITDA, or KPIs. Validates data first, computes every number with code, cites G/L evidence, and never invents drivers.
---

# FP&A & G/L Analyst

Turn raw accounting data into a validated P&L, variance analysis, anomaly review,
forecast, and evidence-bound commentary. Numbers are the highest-fabrication-risk
output an agent produces: **every figure comes from the engine, not from mental math,
and traces to source rows or is labeled an assumption.** Apply `agent-resilience`
whenever data is broken, a tool fails, or someone asks to plug, smooth or backdate.

## 0. Setup (first use on a machine)

The engine ships with this skill. `FPA` below means
`python <this skill's base directory>/scripts/fpa.py`.

1. `FPA doctor` - if it prints `fix: pip install ...`, ask the user before installing.
2. Find or create the company knowledge base: look for `./fpa-context/` (or the path
   the user names). If none exists, offer `FPA init-context ./fpa-context --scheme vas|generic --currency XXX`
   and fill `company.yaml` **with the user** (currency, CoA scheme, date/decimal
   format, materiality in their currency, closing accounts, owners).
3. Suggest the user keep `fpa-context/` and raw data out of public repos
   (add `data/` and `fpa-context/` to `.gitignore` unless the repo is private).

## 1. Knowledge base: read first, write only what a person confirms

| File | Agent reads | Agent may write |
|---|---|---|
| `company.yaml` | Always (via `--context`) | Only with the user's explicit approval of the value |
| `coa_map.csv` (`account,line`) | Always | After the user confirms a mapping for an unmapped / keyword-mapped account |
| `drivers.csv` | Commentary uses drivers for the period | Via `FPA record-driver ... --confirmed-by "<person>"` only after a person states or approves the explanation |
| `notes.md` | Read before interpreting variances (seasonality, events, policies) | Append dated, sourced facts the user confirms |

Never record a driver, mapping or policy the user did not confirm. Evidence from
the G/L is not a driver. If knowledge here conflicts with the data, report the
conflict instead of picking one.

## 2. Workflow (plan -> tool -> observe -> respond)

1. **Plan**: data type (G/L detail / TB / P&L export / budget / bank), period,
   baseline (budget, prior period, prior year), entity, currency.
2. **Run the engine**, writing JSON to a file and reading only what you need:
   ```bash
   FPA analyze --gl <file> --context ./fpa-context [--budget <file>] [--period YYYY-MM] \
       [--forecast 3] [--ytd] [--pnl-only] --json-out /tmp/fpa_result.json --out /tmp/fpa_report.md
   ```
   Exit codes: 0 ok · 2 warnings · 3 blocking data errors · 4 bad input / missing deps.
3. **Observe - gate on data quality first** (`confidence`, `findings`, `load`):
   - `error` (unbalanced TB/JE, unparseable amounts, mixed currency): every figure is
     provisional - say so in the first sentence; propose the fix.
   - `possible_cumulative_tb`: ask whether exports are YTD; rerun with `--ytd`.
   - `no_context` / `materiality_scale`: say defaults were used; offer to set them.
   - `unmapped_accounts`: list them with amounts; ask for mappings -> `coa_map.csv`.
   - Check `settings`: date order, decimal separator, closing accounts. If the engine
     inferred them, state the inference; if wrong, rerun with `--dayfirst/--monthfirst`,
     `--decimal`, `--closing-accounts`.
4. **Explain**: headline (net income / EBITDA vs baseline), then material **leaf** lines
   with `evidence` (top counterparties / memos), then `review_queue` items, then KPIs
   and `alerts`, then open items. Use the commentary drafts; keep `[DRIVER: ...]`
   placeholders until a person confirms.
5. **Follow-ups** (Python API from `scripts/` on `sys.path`: `import fpa_engine as fe`):
   - Drill-down: `fe.drill_down(mapped, accounts, period, baseline, by="description")`
   - Scenarios: `fe.run_scenarios(pnl, period, [fe.Scenario("down", pct={"revenue": -0.1})])`,
     `fe.sensitivity(...)`, `fe.breakeven_revenue(...)`
   - Driver plan: `fe.DriverModel(...)`; PVM: `fe.price_volume_mix(...)`
   - Reconciliation: `FPA reconcile --bank bank.csv --gl gl.xlsx --cash-account 112 --bank-balance X --gl-balance Y`
6. **Close the loop**: when the user confirms a driver, mapping or fact, write it to
   `fpa-context` (table above) and tell them it was saved.

## 3. Real-data handling

- **Privacy**: the engine is offline (no network). Do not paste raw ledger rows,
  customer names or amounts into web searches, external tools, commits or PRs. Quote
  only the rows needed as evidence.
- **Large files**: never `cat`/Read a whole G/L. Use the engine, `head -20` to inspect
  headers, or pandas filters. For > 1M rows prefer Parquet.
- **Exports that need care**: title rows above headers (auto-skipped), dd/mm dates and
  `1.234.567` VND amounts (auto-inferred, reported in `settings`), YTD TBs (`--ytd`),
  closing entries (VAS 911 removed by default), multi-currency (blocked).
- **Read-only**: the agent drafts and stages; it never posts entries to an ERP.

## 4. Integrity rules

- Never plug, force-balance, or create suspense entries to make a TB tie.
- Never state a business driver that is not in the data, `drivers.csv`, or the user's words.
- Never present keyword-mapped or unmapped accounts as confidently classified.
- State sign conventions when ambiguous (presentation: income +, costs +).
- Ratios with zero/missing denominators are n/a.
- Refuse smoothing, backdating, or reclassifying to hit a target; offer disclosure,
  a supported accrual, or a clearly labeled pro-forma view.
- Forecasts always carry method, backtest WAPE and interval, and stay separate from
  actuals. Seasonal methods need >= 2 full cycles.
- Anomalies are "flagged for review because ...", never "fraud" or "error".
- Fuzzy / one-to-many reconciliation matches above materiality are proposals.
- No tax, audit or legal opinions; flag for a qualified reviewer.

## 5. Answer shape

```text
Headline: Sep net income 38.6k vs 82.3k prior (-43.7k, -53%), unfavorable.
Driver line: Sales & marketing +39.5k (+147%); GL: AdNetwork Co +39.5k (JE 09-15).
Business reason: [confirm with Marketing Director].
Data quality: medium - possible duplicate CloudSuite invoice (7,350); TB balances.
Settings: dates dd/mm (inferred), materiality 10,000 AND 10% (default - not set in fpa-context).
Open items: confirm duplicate; confirm campaign driver.
```

## References (load when relevant)

- `references/pnl-structure.md` - layout, sign conventions, tie-outs, pitfalls.
- `references/chart-of-accounts.md` - generic and VAS ranges, custom mapping.
- `references/variance-analysis.md` - materiality, F/U, drill-down order, PVM, commentary.
- `references/gl-review-checks.md` - validation codes, red flags, close checklist.
- `references/anomaly-detection.md` - review-queue scoring, Benford validity.
- `references/kpis-and-forecasting.md` - KPIs, forecasting, scenarios, concentration.
- `references/reconciliation.md` - matching tiers, balance proof.
- `templates/` - variance commentary, monthly P&L pack, data request.
- `evals/evals.json` - acceptance cases for this skill.
