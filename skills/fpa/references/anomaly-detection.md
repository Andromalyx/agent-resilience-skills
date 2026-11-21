# Anomaly Detection on the G/L

Goal: a short, ranked list a reviewer can actually clear, with a reason per row.
Volume of flags is a triage problem, not a model problem: precision@k (how many of
the top k were worth reviewing) is the metric that matters.

## Layers (`runtime.finance.anomaly`)

| Layer | Function | Catches |
|---|---|---|
| Validation rules | `validate_ledger` | Unbalanced TB/JE, exact duplicates, abnormal signs, cut-off |
| Transaction rules | `transaction_flags` | Amount outlier vs same-account history (robust z on log amount), first-time counterparty on an account, near-duplicate (same account + vendor + amount within 7 days), period-end posting, large round amount, weekend |
| Account trend | `account_period_outliers` | Account total far from its own median (robust z = (x - median) / 1.4826·MAD) |
| Digit analysis | `benford_first_digit` | Nigrini MAD conformity + chi-square |
| ML (optional) | `isolation_forest_scores` | Multivariate oddities (amount, timing, frequency) - needs scikit-learn |
| Ranking | `risk_rank` | Weighted rule score x log10(amount) -> top-k with reasons, P&L legs only |

## Weights (default, tune with reviewer feedback)

`amount_outlier 3 · near_duplicate 3 · ml_outlier 2 · new_counterparty 1.5 ·
period_end 1 · round_amount 1 · weekend 0.5`. A row needs score >= 1 to enter the
queue, so a weekend date alone never does.

## Benford - when it is valid

- Needs n >= 300 amounts >= 10, spanning several orders of magnitude.
- Not valid for assigned or capped amounts (rent, payroll, subscriptions, petty cash
  limits) or for small populations - say so instead of reporting "nonconformity".
- MAD thresholds (first digit): < 0.006 close · < 0.012 acceptable · < 0.015 marginal · else nonconformity.

## Operating the screen

1. Run per period; history (all periods) is the reference distribution.
2. Review top-k; record outcome (valid / error / needs support). Feed outcomes back
   into weights or thresholds monthly.
3. After org changes (new ERP, shared-services center), expect flag floods from
   population shift - segment by source or re-baseline, don't suppress.
4. Report language: "flagged for review because X" - never "fraud" or "error".
