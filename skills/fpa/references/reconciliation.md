# Reconciliation (bank / sub-ledger -> G/L)

`runtime.finance.reconcile.reconcile(bank, gl, ...)` - both frames need `date`,
`amount` (receipts positive), optional `reference`, `description`.

## Tiers (matched rows are locked after each tier)

| Tier | Rule | Confidence |
|---|---|---|
| `exact` | Same reference, amount within tolerance, date within ±3 days | Auto-clear |
| `amount_date` | Amount within tolerance, date within ±3 days, exactly one candidate | Auto-clear |
| `fuzzy` | Amount within tolerance, date within ±7 days, description similarity >= 0.8 | Review if >= threshold |
| `one_to_many` | One bank line = sum of 2-5 GL lines (batched deposits) | Review if >= threshold |

Similarity normalizes case/punctuation and noise tokens (PMT, TRF, REF, LTD, INV...);
uses rapidfuzz `token_set_ratio` if installed, else difflib.

## Balance proof

`adjusted bank = bank ending + GL-only items - bank-only items`; must equal GL ending.
`summary["unexplained_difference"]` must be 0 before the rec is called reconciled.
Typical reconciling items: deposits in transit and outstanding cheques (GL-only),
bank fees / interest / direct debits not yet booked (bank-only -> propose JEs).

## Guardrails

- Never match across currencies without FX at transaction-date rate.
- Every match records tier + score; keep it for audit.
- Fuzzy and one-to-many matches above materiality are proposals, not clearances.
- Preparer and reviewer must be different people; the agent prepares only.
- Sample ~25 auto-matches monthly; > 2 errors -> tighten thresholds.
