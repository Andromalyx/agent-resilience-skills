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

## Forecasting patterns

1. **Run-rate**: `run_rate(pnl, "net_revenue", last_3_periods)`; quick, ignores seasonality.
2. **Driver-based**: revenue = units x price, payroll = headcount x loaded cost, S&M =
   % of revenue or campaign calendar. Preferred: each assumption is explicit and owned.
3. **Statistical**: seasonal naive / ETS / Prophet / statsforecast on >= 24 months.
   Report intervals, not just a point.
4. **Scenarios**: base / upside / downside with stated assumption deltas.

Rules: label every forecast assumption; show actuals vs forecast separately; never
backfill missing actuals with forecast values without saying so.
