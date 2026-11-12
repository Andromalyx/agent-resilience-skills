# Agent Resilience Skills

Agent Resilience Skills is a reusable AI agent skill for staying calm, honest, adaptive, and task-focused when work gets difficult. It gives agents a compact operating pattern for pressure, ambiguity, tool failures, user frustration, impossible requests, and hallucination risk.

The goal is simple: an agent should not panic, fabricate, hide failure, or pretend completion. It should notice stress and failure signals, run an integrity checkpoint, reframe the obstacle, recover with the next correct action, and respond truthfully.

## What This Skill Provides

- Activation rules for detecting pressure, uncertainty, tool failure, user frustration, impossible tasks, and fabrication risk.
- Stress-level classification and agent-flow guidance for low-risk versus elevated-risk paths.
- An integrity checkpoint that forces the agent to separate known facts, assumptions, missing evidence, and next actions.
- Support selection for deciding when to search, inspect files, calculate, cite, ask, apply policy, or escalate.
- Completion evaluation to prevent unverified "done" claims.
- Recovery patterns for calm repair, uncertainty disclosure, tool failure recovery, user frustration repair, and anti-fabrication.
- Portable adapters for Codex, ChatGPT, Claude Code, OpenClaw, and generic agent runtimes.
- Lightweight Python helpers for detection, integrity checking, and recovery planning.
- Starter eval datasets, rubrics, and tests.

## FP&A & G/L Analyst Skill (`skills/fpa`)

A technical skill that pairs with resilience: it reads your general ledger or trial
balance, builds the management P&L, explains variances with G/L evidence, and drafts
commentary **without inventing drivers**.

```bash
python -m pip install -e ".[finance]"
python -m runtime.finance --gl examples/finance/sample_gl.csv                       # vs prior month
python -m runtime.finance --gl examples/finance/sample_gl.csv \
    --budget examples/finance/sample_budget.csv --out pnl_review.md                 # vs budget
python -m runtime.finance --gl my_gl.xlsx --scheme vas --mapping my_coa_map.csv     # Vietnam VAS
```

```python
from runtime.finance import analyze

result = analyze("my_gl.csv", period="2026-09", budget="budget.csv", materiality_abs=5_000)
print(result.confidence)          # gated by data-quality checks
print(result.variance.query("material"))
print(result.to_markdown())       # P&L pack: data quality, P&L, variance, commentary, open items
```

Pipeline: load (EN/VI headers, `(1,234)` negatives) -> CoA mapping with provenance
(`explicit > range > keyword > unmapped`) -> validation (TB/JE balance, duplicates,
abnormal signs, cut-off, round amounts) -> P&L (net revenue ... net income, margins) ->
variance (F/U, materiality, new/dropped/sign-flip) -> G/L drill-down -> commentary.
See `skills/fpa/SKILL.md` and `examples/finance/README.md`.

## Core Behavior

When resilience is activated, the agent should follow this loop:

1. Interpret the user request.
2. Detect the pressure or failure signal and classify stress level.
3. Pause, stabilize tone, and run an integrity checkpoint.
4. State what is known, unknown, blocked, or risky.
5. Reframe the problem into the next recoverable action.
6. Use tools, sources, clarification, policy, or escalation when needed.
7. Continue with a calm, truthful response.
8. Never claim completion unless completion is verified.

## Repository Layout

```text
skills/resilience/        Main reusable skill content.
skills/fpa/               FP&A & G/L analyst skill (references + templates).
adapters/                 Platform-specific instruction adapters.
runtime/                  Small Python runtime helpers.
runtime/finance/          Pandas toolkit: GL/TB -> P&L, variance, KPIs, commentary, CLI.
evals/                    Starter datasets and rubrics.
docs/                     Conceptual and implementation documentation.
tests/                    Unit tests for runtime behavior.
examples/                 Example agent integrations.
```

## Quick Start

Install the project in editable mode and run tests:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Use the Python helpers directly:

```python
from runtime import assess_resilience

result = assess_resilience(
    "The tool failed twice and the user is angry. I am not sure the data is complete."
)

print(result.plan.response_pattern)
print(result.plan.next_action)
```

Use the skill in an agent by copying or referencing:

- `skills/resilience/SKILL.md` for the canonical skill.
- `adapters/codex/AGENTS.md` for Codex-style coding agents.
- `adapters/generic-agent/system-prompt.md` for general system prompts.

## Design Principles

- Truth over fluency: disclose uncertainty and failure plainly.
- Recovery over apology loops: acknowledge the issue, then move to the next correct action.
- Calm tone under pressure: use precise, non-defensive language.
- Support over guessing: verify with available resources when accuracy depends on it.
- Verifiable completion: only say work is done when it has been checked.
- Minimal mechanism: keep the first version understandable and easy to adapt.

## Production Use

Before using this skill in production:

- Add domain-specific activation signals.
- Tune refusal and escalation policies for your risk profile.
- Connect the integrity checkpoint to your tool logs, retrieval layer, or audit trail.
- Run scenario evals that represent your real users and failure modes.
- Monitor for false confidence, hidden tool failures, and unresolved user frustration.

## Status

Initial scaffold. APIs and docs may evolve before a stable release.

## License

MIT. See [LICENSE](LICENSE).
