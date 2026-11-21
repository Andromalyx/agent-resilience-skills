# Finance examples

| File | What |
|---|---|
| `generate_sample_data.py` | Deterministic balanced G/L (Jul-Sep 2026) + Sep budget with planted issues |
| `sample_gl.csv` / `sample_budget.csv` | Generated output (QuickBooks-style headers) |
| `sample_gl_history.csv` | 27 months, seasonal (Q4 peak), planted Sep anomalies - for forecast / anomaly demos |
| `langgraph_fpa_agent.py` | LangGraph ReAct agent exposing the toolkit as tools, `skills/fpa/SKILL.md` as system prompt |

## Using your own data

1. Export G/L detail (preferred) or a **periodic** trial balance to CSV/XLSX with: date or
   period, account, account name, debit + credit (or one signed amount), JE id, memo,
   vendor/customer, department. Headers are auto-detected (EN + VI, e.g. `Số tài khoản`,
   `Phát sinh nợ`); override with `column_map` if needed.
2. If your CoA isn't `generic` (US 4-digit) or `vas` (Circular 200), write a mapping CSV
   (`account,line`) - see `skills/fpa/references/chart-of-accounts.md`.
3. Run: `python -m runtime.finance --gl your_gl.csv --mapping map.csv --out review.md`.
   Use `--pnl-only` for P&L-only extracts (TB won't balance by design).
4. Check the **Data quality** section first: it sets the confidence of everything below.

Pitfalls: YTD (cumulative) TB exports must be converted to monthly movements; remove
year-end closing entries (VAS 911); never sum mixed currencies.

## Agent

```bash
pip install -e ".[finance,ml,agent]"
export ANTHROPIC_API_KEY=...
python examples/finance/langgraph_fpa_agent.py --gl examples/finance/sample_gl.csv \
  "Why did net income drop in September, and is anything in the data suspicious?"
python examples/finance/langgraph_fpa_agent.py --gl examples/finance/sample_gl_history.csv \
  "Forecast Q4 revenue and tell me what a 10% revenue drop does to EBITDA."
```

Production notes: put the ledger behind a read-only connector (ERP API / warehouse view),
keep tools deterministic (the LLM narrates, pandas computes), log every tool call for
audit, and keep a human sign-off before anything goes into a board pack.
