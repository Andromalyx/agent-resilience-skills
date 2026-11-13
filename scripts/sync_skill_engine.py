"""Copy runtime/finance into skills/fpa/scripts/fpa_engine so the skill is self-contained.

Run after changing runtime/finance:  python scripts/sync_skill_engine.py
`--check` exits 1 if the vendored copy has drifted (used by tests / CI).
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "runtime" / "finance"
DST = ROOT / "skills" / "fpa" / "scripts" / "fpa_engine"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def _files(base: Path) -> set[str]:
    return {str(p.relative_to(base)) for p in base.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def drift() -> list[str]:
    if not DST.exists():
        return ["<vendored engine missing>"]
    src, dst = _files(SRC), _files(DST)
    diffs = sorted(src ^ dst)
    diffs += sorted(f for f in src & dst if not filecmp.cmp(SRC / f, DST / f, shallow=False))
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        d = drift()
        if d:
            print("vendored engine drifted:", *d, sep="\n  ")
            return 1
        print("vendored engine in sync")
        return 0
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST, ignore=IGNORE)
    print(f"synced {len(_files(DST))} files -> {DST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
