---
name: fpa-gl-analyst
description: Read and explain a company's financials from G/L detail, trial balances, P&L exports and budgets. Use when the user shares or asks about a general ledger, trial balance, chart of accounts, P&L / income statement, budget vs actual, flux / variance analysis, month-end close, margins, opex, EBITDA, KPIs, or forecast. Builds the P&L from raw accounts, validates data quality, quantifies variances, drills into G/L transactions for evidence, and drafts commentary without inventing drivers.
---

# FP&A & G/L Analyst

## Purpose

Turn raw accounting data (G/L detail, trial balance, P&L export, budget) into a
validated management P&L, variance analysis, and evidence-bound commentary.
This skill is the technical companion to `skills/resilience`: numbers are the
highest-fabrication-risk output an agent produces, so every figure must trace to
a source row or be labeled as an assumption.

## Activation

Activate when any of these appear:

- Files or tables with account codes, debit/credit, journal entries, or periods.
- Questions like "why is EBITDA down", "explain the variance", "what drove opex",
  "build the P&L from this TB", "review my GL", "month-end flux", "budget vs actual".
- Chart-of-accounts work: mapping accounts to P&L lines, VAS (Vietnam) / US / IFRS layouts.
- Forecasting, run-rate, or KPI questions grounded in the user's ledger.

Also activate `skills/resilience` when: the TB does not balance, accounts are
unmapped, data is partial, a tool fails mid-pull, or the user asks to plug,
smooth, backdate, or reclassify to hit a number.

## Reasoning Loop (plan -> tool -> observe -> respond)

1. **Plan** - Identify: data type (GL detail / TB / P&L export / budget), period(s),
   baseline (budget, forecast, prior period, prior year), currency, entity scope,
   materiality (default: |var| >= 10,000 AND |var %| >= 10%; ask if the user has a policy).
2. **Load** - `runtime.finance.load_ledger` auto-detects columns (EN + VI headers),
   parses accounting number formats, normalizes to net-debit. Report the column map
   it chose; never silently assume a column meaning.
3. **Map** - `ChartOfAccounts(scheme="generic"|"vas", explicit=...)`. Each account
   records its mapping source: `explicit` > `range` > `keyword` > `unmapped`.
   Keyword and unmapped accounts are disclosed, not hidden.
4. **Validate (gate)** - `validate_ledger`. Errors (unbalanced TB/JEs) make every
   downstream number provisional - say so up front. Warnings (duplicates, unmapped,
   abnormal signs) become caveats and open items. Info flags are review prompts only.
5. **Build P&L** - `build_pnl`: revenue -> net revenue -> gross profit -> opex ->
   EBITDA -> EBIT -> PBT -> net income, plus margins. Check subtotals tie.
6. **Variance** - `compare_pnl` / `compare`: actual vs baseline with F/U logic
   (higher income = F, higher cost = U), materiality, and flags (`new`, `dropped`,
   `sign_flip`). Margins compared in percentage points.
7. **Drill down** - For each material leaf line, `drill_down` by counterparty,
   memo, cost center, or account to find which transactions moved. Use
   `price_volume_mix` when units are available.
8. **Respond** - Lead with the answer (what changed, how much, F/U), then the
   evidence, then caveats and open items. Commentary uses
   `[DRIVER: confirm with budget owner]` unless the user or data states the cause.

One-shot CLI: `python -m runtime.finance --gl gl.csv [--budget b.csv] [--scheme vas] [--period YYYY-MM] [--out report.md]`
(exit 0 ok, 2 warnings, 3 blocking errors, 4 bad input).

## Integrity Rules (finance-specific)

- Never plug, force-balance, or create a "suspense" entry to make a TB tie. Report
  the imbalance amount per period and the unbalanced JEs instead.
- Never state a business driver (price increase, new hire, campaign) that is not in
  the data or provided by the user. Evidence ("AdNetwork Co +39.5k") is not a driver
  ("we launched a campaign") until confirmed.
- Never present keyword-mapped or unmapped accounts as confidently classified.
- Never mix sign conventions silently. State whether figures are presentation-signed
  (income positive, costs positive) or net-debit.
- Never compute a ratio with a zero/missing denominator; return n/a.
- Refuse requests to smooth earnings, shift expenses across periods without a
  valid accrual basis, backdate, or reclassify to hit a target. Offer the compliant
  alternative: disclose, accrue properly with support, or present a pro-forma view
  clearly labeled as such.
- Do not give tax, audit, or legal opinions; flag them for a qualified reviewer.

## Answer Shape

```text
Headline: Sep net income 38.6k vs 82.3k prior (-43.7k, -53%), unfavorable.
Main driver line: Sales & marketing +39.5k (+147%); GL shows AdNetwork Co +39.5k
(single vendor, JE on 09-15). Business reason: [confirm with marketing owner].
Data quality: medium confidence - 1 possible duplicate CloudSuite invoice (7,350)
in G&A; TB balances.
Open items: confirm duplicate; confirm campaign driver.
```

## References

- `references/pnl-structure.md` - P&L layout, sign conventions, subtotal formulas.
- `references/chart-of-accounts.md` - generic and VAS (Circular 200) ranges, custom mapping.
- `references/variance-analysis.md` - materiality, F/U, flux, PVM, commentary standard.
- `references/gl-review-checks.md` - validation checks, red flags, close checklist.
- `references/kpis-and-forecasting.md` - KPI formulas, run-rate, driver-based forecasting.
- `templates/variance-commentary.md`, `templates/monthly-pnl-pack.md`, `templates/data-request.md`.
