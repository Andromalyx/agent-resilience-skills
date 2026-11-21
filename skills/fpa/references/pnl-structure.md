# P&L Structure & Sign Conventions

## Sign conventions

| Convention | Revenue | Expense | Where you see it |
|---|---|---|---|
| Net debit (ledger) | negative | positive | GL detail, TB, ERP exports (`debit - credit`) |
| Natural / presentation | positive | positive | Budgets, board packs, management P&L |
| Signed profit impact | positive | negative | Some BI tools, variance bridges |

The toolkit stores **net debit** internally and presents **natural** sign. Budget
files are usually natural sign - load with `amount_sign="natural"` and convert
via `natural_to_net_debit`. Contra-revenue (discounts, returns) is debit-normal:
a positive natural discount *reduces* revenue.

Always tell the user which convention a number is in when it is ambiguous.

## Layout & formulas

```
Revenue
- Discounts, returns & allowances (contra revenue)
= Net revenue
- COGS
= Gross profit                         GM% = GP / Net revenue
- Opex (personnel, S&M, R&D, facilities, G&A)
= EBITDA                               EBITDA% = EBITDA / Net revenue
- Depreciation & amortization
= EBIT (operating income)
+ Other / financial income
- Interest & financial expense
- Other expense
= Profit before tax (PBT)
- Income tax                           ETR = Tax / PBT
= Net income                           NM% = NI / Net revenue
```

Tie-out checks the agent must run before presenting:

1. Sum of all P&L line net-debits for a period == -Net income.
2. If a full TB is supplied: net income == change in retained earnings before
   closing entries (or the 911 / income-summary account balance for VAS).
3. Subtotals recompute from their components (no hard-coded subtotals from exports).

## Common pitfalls

- **Closing entries in the extract**: year-end closing to retained earnings (or VAS
  911) zeroes out P&L accounts. Exclude closing JEs or the P&L shows zero.
- **Cumulative vs periodic TB**: many ERPs export YTD balances. Convert to periodic
  (`month_n - month_{n-1}`) before monthly variance work.
- **Multi-currency**: never sum different currencies. Ask for functional-currency
  amounts or rates.
- **Intercompany**: consolidations must eliminate IC revenue/COGS; flag IC accounts.
- **EBITDA definitions differ** (adjusted EBITDA, IFRS 16 rent): state the definition.
