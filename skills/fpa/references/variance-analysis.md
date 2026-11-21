# Variance & Flux Analysis

## Baselines

| Baseline | Answers | Notes |
|---|---|---|
| Budget / plan | "Are we on plan?" | Budget has no transactions: evidence must come from GL vs prior or from owners |
| Latest forecast | "Is the forecast still right?" | Preferred for in-year steering |
| Prior period (MoM) | "What moved this month?" (flux) | GL drill-down available |
| Prior year (YoY) | Seasonality-adjusted trend | Watch for CoA changes between years |

## Materiality

Default: `|variance| >= 10,000 AND |variance %| >= 10%` (`rule="and"`, typical close
flux policy). Use `rule="or"` for board-level reviews where a big % on a small line
still matters. Always state the threshold used. New / dropped lines (baseline 0)
have undefined % and are treated as breaching the % test.

## Favorable / unfavorable

- Income lines and profit subtotals: actual > baseline = **F**.
- Cost lines: actual < baseline = **F**.
- Margins: compare in **percentage points**, not % of %.
- Flags: `new`, `dropped`, `sign_flip` (e.g., expense turned negative - reversal?).

## Drill-down order

1. Which **P&L line**? (leaf lines, not subtotals - subtotals just restate the money)
2. Which **accounts** under the line?
3. Which **counterparties / memos / cost centers / JEs**? (`drill_down(..., by=...)`)
4. Is it **timing** (accrual vs cash, late invoice, prior-period true-up), **one-off**
   (duplicate, reclass, error), or **run-rate** (recurring change)?
5. For revenue/COGS with units: **price / volume / mix** (`price_volume_mix`).

## Price-volume-mix

```
volume_i = (Q_a_total - Q_b_total) * mix_b_i * P_b_i
mix_i    = (mix_a_i - mix_b_i) * Q_a_total * P_b_i
price_i  = (P_a_i - P_b_i) * Q_a_i
volume + mix + price == Rev_a - Rev_b   (asserted by the toolkit)
```

## Commentary standard (each material line)

`What` (line, amount, %, F/U) -> `Evidence` (top GL contributors) -> `Why` (driver
confirmed by owner, else placeholder) -> `So what` (one-off vs run-rate, forecast
impact) -> `Action` (owner, date).

Bad: "Marketing over budget due to higher spend."
Good: "S&M +38.3k (+137%) U vs budget. GL: AdNetwork Co +39.5k on JE 09-15 (single
invoice). Driver: [confirm with marketing]. If a one-off campaign, Q4 forecast
unaffected; if run-rate, FY opex +115k."
