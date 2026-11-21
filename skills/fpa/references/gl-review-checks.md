# G/L Review Checks & Close Checklist

## Automated checks (`validate_ledger`)

| Code | Severity | Meaning | Agent action |
|---|---|---|---|
| `tb_out_of_balance` | error (info for P&L-only extracts) | Debits != credits per period | Report amount per period; do **not** plug |
| `je_unbalanced` | error | A journal entry doesn't net to zero | List JE ids; likely truncated export |
| `possible_duplicates` | warning | Identical date/account/amount/memo/JE | Ask to confirm double post; quantify impact |
| `unmapped_accounts` | warning | Account excluded from P&L | Ask for mapping; show net amount excluded |
| `abnormal_balances` | warning | Income with debit balance / expense with credit | Check reversals, reclasses, mis-postings |
| `keyword_mapped_accounts` | info | Mapped by name only | Confirm mapping |
| `weekend_postings` | info | Posted Sat/Sun | Review flag only (fraud-risk heuristic, often benign) |
| `date_period_mismatch` | info | Posting date outside its period | Accrual / late posting - affects cut-off |
| `round_amounts` | info | Large round numbers | Estimates / manual JEs - ask for support |

## Manual red flags to look for

- Large manual JEs near period end, especially to revenue or reserves.
- Reversals in the first days of next period (window dressing).
- Revenue up while AR days / DSO jump (collectability, channel stuffing).
- Expense accounts with credit balances; suspense / clearing accounts with balances.
- Same preparer and approver on material JEs (segregation of duties).
- Accruals that never reverse; prepaids that never amortize.

## Month-end close checklist (FP&A view)

1. Sub-ledgers closed (AR, AP, FA, inventory, payroll) and tied to GL control accounts.
2. Bank reconciliations complete; unreconciled items aged.
3. Accruals & prepaids booked and supported; prior-month accruals reversed.
4. Depreciation / amortization run.
5. Intercompany matched and eliminated.
6. Revenue cut-off tested.
7. TB balances; P&L ties to retained-earnings movement.
8. Flux review: all material variances explained with evidence + owner-confirmed driver.
9. Management pack reviewed by someone other than the preparer.

The agent drafts and stages; a human signs off. It never posts entries.
