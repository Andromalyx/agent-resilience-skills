# Claude Code Adapter

Use Agent Resilience Skills for repository work when commands fail, requirements are ambiguous, tests cannot be verified, or the user corrects the agent.

## FP&A & G/L Analyst

`skills/fpa/SKILL.md` has Claude Code skill frontmatter and can be installed directly:

```bash
pip install -e ".[finance]"                                  # makes runtime.finance importable
mkdir -p ~/.claude/skills && cp -r skills/fpa ~/.claude/skills/fpa-gl-analyst
```

Claude Code then loads it when you share a G/L, trial balance, P&L or budget, and runs
`python -m runtime.finance ...` for deterministic numbers instead of computing in-context.
