"""LangGraph ReAct agent that answers questions about *your* G/L using runtime.finance tools.

Reasoning loop:
    plan     -> model reads the question + skills/fpa/SKILL.md (system prompt)
    tool     -> load_and_validate / pnl / variance / drill_down (deterministic pandas)
    observe  -> tool JSON (validation findings gate confidence)
    respond  -> answer with numbers + evidence + caveats, no invented drivers

State: the loaded ledger lives in a process-local cache keyed by file path (tools stay
stateless and JSON-serializable); conversation memory via LangGraph MemorySaver.

Run:
    pip install -e ".[finance,agent]"
    export ANTHROPIC_API_KEY=...
    python examples/finance/langgraph_fpa_agent.py \
        --gl examples/finance/sample_gl.csv "Why did net income drop in September?"
"""

from __future__ import annotations

import argparse
import json
import logging
from functools import lru_cache
from pathlib import Path

import pandas as pd
from langchain_core.tools import tool

from runtime.finance import (
    ChartOfAccounts,
    analyze,
    attach_lines,
    build_pnl,
    drill_down,
    load_ledger,
    validate_ledger,
)

logger = logging.getLogger("fpa_agent")
ROOT = Path(__file__).resolve().parents[2]
SKILL = (ROOT / "skills" / "fpa" / "SKILL.md").read_text(encoding="utf-8")
DEFAULT_MODEL = "claude-sonnet-5-5"


@lru_cache(maxsize=8)
def _mapped(path: str, scheme: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load + map once per (path, scheme); tools reuse the cached frames."""
    ledger, _ = load_ledger(path)
    mapping = ChartOfAccounts(scheme=scheme).classify_frame(ledger)
    return attach_lines(ledger, mapping), mapping


def _jsonable(df: pd.DataFrame, max_rows: int = 40) -> str:
    return df.head(max_rows).round(2).to_json(orient="table", default_handler=str)


@tool
def load_and_validate(path: str, scheme: str = "generic", pnl_only: bool = False) -> str:
    """Load a G/L or trial balance file and run data-quality checks. Call this FIRST."""
    try:
        mapped, mapping = _mapped(path, scheme)
    except (FileNotFoundError, ValueError) as exc:
        return json.dumps({"error": str(exc)})
    report = validate_ledger(mapped, mapping, expect_balanced=not pnl_only)
    return json.dumps({
        "rows": len(mapped),
        "periods": sorted(mapped["period"].unique().tolist()),
        "blocking_errors": not report.ok,
        "findings": report.to_frame().to_dict("records"),
        "mapping_sources": mapping["source"].value_counts().to_dict(),
    })


@tool
def pnl(path: str, scheme: str = "generic") -> str:
    """Management P&L (lines, subtotals, margins) by period, presentation-signed."""
    mapped, _ = _mapped(path, scheme)
    return _jsonable(build_pnl(mapped))


@tool
def variance(path: str, period: str, budget_path: str | None = None,
             scheme: str = "generic", materiality_abs: float = 10_000,
             materiality_pct: float = 10.0) -> str:
    """Variance of `period` vs budget (if budget_path) or prior period, with draft commentary."""
    try:
        a = analyze(path, period=period, budget=budget_path, scheme=scheme,
                    materiality_abs=materiality_abs, materiality_pct=materiality_pct)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({
        "baseline": a.baseline_name, "baseline_period": a.baseline_period,
        "confidence": a.confidence, "variance": json.loads(_jsonable(a.variance)),
        "commentary_draft": a.commentary,
    })


@tool
def gl_drill_down(path: str, line: str, period: str, baseline_period: str,
                  by: str = "counterparty", scheme: str = "generic") -> str:
    """Top G/L contributors to a P&L line's change between two periods.
    `line` is a P&L line key, e.g. opex_sales_marketing. `by`: counterparty|description|
    cost_center|account|entry_id. Values are net-debit (cost increase = positive)."""
    mapped, mapping = _mapped(path, scheme)
    accounts = mapping.loc[mapping["line"] == line, "account"].tolist()
    if not accounts:
        return json.dumps({"error": f"No accounts mapped to {line!r}"})
    return _jsonable(drill_down(mapped, accounts, period, baseline_period, by=by))


TOOLS = [load_and_validate, pnl, variance, gl_drill_down]


def build_agent(model: str = DEFAULT_MODEL):
    """Compile a ReAct graph with checkpointed memory."""
    from langchain_anthropic import ChatAnthropic
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.prebuilt import create_react_agent

    llm = ChatAnthropic(model=model, max_tokens=4096, max_retries=3, timeout=120)
    return create_react_agent(llm, TOOLS, prompt=SKILL, checkpointer=MemorySaver())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gl", required=True)
    parser.add_argument("--budget")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("question")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    agent = build_agent(args.model)
    msg = f"G/L file: {args.gl}" + (f"\nBudget file: {args.budget}" if args.budget else "")
    msg += f"\n\n{args.question}"
    result = agent.invoke({"messages": [("user", msg)]},
                          config={"configurable": {"thread_id": "cli"}, "recursion_limit": 25})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
