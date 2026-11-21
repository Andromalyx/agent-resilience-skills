# Using the FP&A skill in Claude Code with real data

## 1. Install

Option A - plugin (both skills, auto-updates with the repo):

```text
/plugin marketplace add Andromalyx/agent-resilience-skills
/plugin install agent-resilience-skills@agent-resilience-skills
```

Option B - copy just the FP&A skill (self-contained, engine bundled):

```bash
mkdir -p ~/.claude/skills
cp -r skills/fpa ~/.claude/skills/fpa-gl-analyst          # personal, all projects
# or: cp -r skills/fpa <your-project>/.claude/skills/fpa-gl-analyst   (project only)
```

Python deps on the machine running Claude Code (once):

```bash
python -m pip install pandas numpy openpyxl pyyaml      # required
python -m pip install scikit-learn rapidfuzz            # optional: ML anomaly score, fuzzy recon
python ~/.claude/skills/fpa-gl-analyst/scripts/fpa.py doctor
```

## 2. Lay out a finance workspace

```text
my-finance/                  # open Claude Code here
  .gitignore                 # data/  fpa-context/  reports/   (unless the repo is private)
  data/                      # raw exports: gl_2026.xlsx, tb_2026-09.csv, budget_2026.csv, bank_09.csv
  fpa-context/               # knowledge base about YOUR books (see below)
  reports/                   # generated packs
```

Create the knowledge base and fill it once, with your accountant if possible:

```bash
python ~/.claude/skills/fpa-gl-analyst/scripts/fpa.py init-context fpa-context --scheme vas --currency VND
```

| File | Fill with |
|---|---|
| `company.yaml` | currency, `scheme` (vas/generic), `date_order`, `decimal`, materiality **in your currency**, closing accounts (VAS 911), fiscal year start, owners per P&L line |
| `coa_map.csv` | every account the default scheme maps wrongly or not at all (`account,line`) |
| `notes.md` | business model, seasonality (Tet, Q4), annual one-offs, accounting policies, known quirks |
| `drivers.csv` | leave empty - Claude appends owner-confirmed variance explanations over time |

## 3. First real run (calibration)

Ask Claude: *"Review data/gl_2026.xlsx for September using fpa-context."* Then check,
before trusting anything:

1. **Settings line** in the report: date order, decimal separator, scheme, materiality,
   closing accounts - are they right for your export?
2. **Unmapped / keyword-mapped accounts** - map them in `coa_map.csv`.
3. **Tie-out**: compare revenue, gross profit and net income for one closed month
   with your official management accounts or VAS B02-DN. Differences usually mean a
   mapping, closing-entry or YTD issue - fix in `fpa-context`, not by hand.
4. **Anomaly queue**: whitelist known-benign counterparties (intercompany) in
   `company.yaml`.

Once one month ties out, the setup is calibrated; later months reuse it.

## 4. Day-to-day prompts

- "Why did EBITDA drop in October vs September? Show GL evidence."
- "Compare Q3 to budget (data/budget_2026.csv) and draft board commentary."
- "Anything unusual in October postings?"
- "Forecast revenue for the next 3 months and show a 10% downside."
- "Reconcile data/bank_10.csv to cash account 1121 - bank closing 1,234,567,890."
- "Marketing confirmed the October spike was the Tet campaign - record it."

## 5. What stays manual (by design)

- Posting entries, approving reconciliations, signing off packs - human only.
- Drivers, mappings, policies - recorded only when a person confirms them.
- Tax / audit / legal conclusions - out of scope.

## 6. Known limits

- Single entity per run; no intercompany elimination or consolidation.
- No live ERP connector: export files (CSV/XLSX/Parquet).
- Statistical forecasts need >= 24 months for seasonal methods.
- Defaults for anomaly weights and KPI alert thresholds are generic - tune them.
- Validate the first runs against known-good numbers (section 3) before relying on output.
