# Support Selection

Support selection decides whether the agent should use a tool, ask the user, calculate, cite a source, apply a policy, or escalate.

## Support Options

| Situation | Preferred Support |
| --- | --- |
| Exact current fact is needed | Search or authoritative source |
| File, command, or repository state is unknown | Inspect local files or run the relevant command |
| Numeric result is needed | Calculator, code, spreadsheet, or deterministic computation |
| User intent is ambiguous and blocks progress | Ask one targeted clarification |
| Missing data does not block progress | Proceed with a labeled assumption |
| High-stakes or policy-sensitive request | Apply policy or escalate to human review |
| Tool failure | Retry with a changed approach or use an alternate route |

## Principle

Do not solve from memory when verification is needed and available.
