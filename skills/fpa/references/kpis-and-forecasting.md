# KPIs & Forecasting

## P&L KPIs (`pnl_kpis`)

| KPI | Formula |
|---|---|
| Gross margin % | Gross profit / Net revenue |
| EBITDA margin % | EBITDA / Net revenue |
| Net margin % | Net income / Net revenue |
| Opex ratio % | Total opex / Net revenue |
| Personnel ratio % | Personnel / Net revenue |
| Effective tax rate % | Income tax / PBT (monthly provisions often distort this) |
| Revenue growth % | (Rev_t - Rev_t-1) / abs(Rev_t-1) |
| Operating leverage | %ΔEBIT / %ΔRevenue (meaningless when revenue change ~0) |

## Working-capital KPIs (`working_capital_kpis`) - needs explicit balances

| KPI | Formula |
|---|---|
| DSO | AR / Revenue x days |
| DIO | Inventory / COGS x days |
| DPO | AP / COGS x days |
| CCC | DSO + DIO - DPO |
| Current ratio | Current assets / Current liabilities |

Missing inputs return NaN - never impute.

## SaaS / subscription (compute only if the data supports it)

ARR / MRR, net revenue retention, gross churn, CAC payback, Rule of 40,
burn multiple (net burn / net new ARR). Ask for subscription data; the GL alone
rarely supports these.

## Concentration, runway, alerts

| Function | Output |
|---|---|
| `revenue_concentration` | Share by customer, HHI (<1,500 low, 1,500-2,500 moderate, >2,500 high); top customer > 25% = key-customer risk |
| `runway_months(cash, net_burn)` | Months of cash at constant burn |
| `kpi_alerts(kpis, thresholds)` | Rule-based health flags; defaults are generic - set per business |

## Forecasting patterns

1. **Run-rate**: `run_rate(pnl, "net_revenue", last_3_periods)`; quick, ignores seasonality.
2. **Statistical baseline** (`auto_forecast`, `forecast_pnl`): backtests naive, 3-month
   moving average, linear trend, seasonal naive, Holt-Winters (additive) with
   rolling-origin folds covering up to a full season; picks the lowest WAPE. Intervals
   are empirical (quantile of backtest |error|), non-narrowing with horizon.
   `forecast_pnl` forecasts each line then rebuilds subtotals so they tie.
   For >= 36 months or many series, `statsforecast` (AutoETS/AutoARIMA) or Prophet are
   good upgrades; keep the same backtest-and-report discipline.
3. **Driver-based** (`DriverModel`): revenue = units x price, payroll = headcount x
   loaded cost, COGS = % of revenue, fixed + growth. Preferred for budgets: each
   assumption is explicit and owned.
4. **Seasonality** (`seasonality_index`): month index (100 = average); range > 50 pts
   = strongly seasonal; < 20 pts = flat. Needs >= 12 months, preferably 24+.

## Scenarios & sensitivity

- `run_scenarios(pnl, period, [Scenario("downside", pct={"revenue": -0.1})])` -
  COGS follows revenue unless shocked (keeps GM%). Subtotals recomputed, so they tie.
- `sensitivity(pnl, period, shock=0.1)` - tornado table of net income impact per line.
- `breakeven_revenue(pnl, period)` - EBIT = 0 with COGS variable, opex/D&A fixed.
- State every assumption next to the scenario; never present a scenario as a forecast.

Rules: label every forecast assumption; show actuals vs forecast separately; never
backfill missing actuals with forecast values without saying so.
