# Claude Code Adapter

Use Agent Resilience Skills for repository work when commands fail, requirements are ambiguous, tests cannot be verified, or the user corrects the agent.

## FP&A & G/L Analyst

Install as a plugin (`/plugin marketplace add Andromalyx/agent-resilience-skills`, then
`/plugin install agent-resilience-skills@agent-resilience-skills`) or copy
`skills/fpa` to `~/.claude/skills/fpa-gl-analyst`. The engine is bundled in
`skills/fpa/scripts/` - only `pandas numpy openpyxl pyyaml` are needed. Real-data setup
(fpa-context knowledge base, calibration, privacy): `docs/claude-code-setup.md`.
