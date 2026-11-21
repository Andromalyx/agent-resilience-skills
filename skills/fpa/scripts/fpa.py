#!/usr/bin/env python3
"""Self-contained launcher for the FP&A engine bundled with this skill.

    python <skill_dir>/scripts/fpa.py doctor
    python <skill_dir>/scripts/fpa.py init-context ./fpa-context --scheme vas --currency VND
    python <skill_dir>/scripts/fpa.py analyze --gl data/gl.xlsx --context ./fpa-context --json-out out.json
    python <skill_dir>/scripts/fpa.py record-driver ./fpa-context --period 2026-09 \
        --line opex_sales_marketing --driver "Q3 campaign" --confirmed-by "Marketing Director"
    python <skill_dir>/scripts/fpa.py reconcile --bank bank.csv --gl gl.csv --cash-account 112

Needs only: pandas, numpy, openpyxl (xlsx), pyyaml (fpa-context). Data never leaves
the machine: no network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import numpy  # noqa: F401
    import pandas  # noqa: F401
except ImportError:
    print("error: the FP&A engine needs pandas and numpy.\n"
          "fix:   python -m pip install pandas numpy openpyxl pyyaml", file=sys.stderr)
    raise SystemExit(4) from None

from fpa_engine.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
