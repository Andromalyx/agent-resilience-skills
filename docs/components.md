# Skill Components

Agent Resilience Skills is organized around seven components.

| Component | Purpose | Current Implementation |
| --- | --- | --- |
| Stress detector | Detects uncertainty, pressure, conflict, failure, or user frustration. | `runtime/resilience_detector.py` |
| Regulation policy | Controls tone and prevents defensive or rushed responses. | `runtime/regulation_policy.py` and `skills/resilience/regulation-policy.md` |
| Integrity checker | Prevents fabrication, false completion, and hidden failures. | `runtime/integrity_guard.py` |
| Reframing engine | Converts obstacles into next-step plans. | Kept inside `runtime/recovery_planner.py` for v1. |
| Recovery planner | Chooses what to do after failure or missing data. | `runtime/recovery_planner.py` |
| Support selector | Decides whether to search, ask, calculate, cite, or escalate. | `runtime/support_selector.py` |
| Completion evaluator | Checks whether the task was done honestly and usefully. | `runtime/completion_evaluator.py` |

## Design Note

The first version keeps the runtime small. Reframing remains part of recovery planning until there is enough complexity to justify a separate engine.
