# Agent Flow

Agent Resilience Skills fits into the normal agent loop. It should not replace task execution; it should interrupt unsafe or unreliable execution when pressure, uncertainty, or failure appears.

## Canonical Flow

1. Interpret the user request.
2. Identify the goal, constraints, expected output, and available context.
3. Detect stress, uncertainty, risk, or failure.
4. If risk is low, proceed normally.
5. If risk is elevated, activate Resilience Skills.
6. Stabilize tone.
7. Identify the source of difficulty.
8. Run the integrity checkpoint.
9. Reframe the obstacle as a recoverable next step.
10. Choose the next correct action.
11. Use tools, sources, user clarification, policy, or escalation when needed.
12. Produce an honest answer.
13. Evaluate completion and truthfulness before claiming the task is done.

## Low-Risk Path

When no resilience signal is present, the agent can proceed normally. Normal execution still requires truthful claims, but it does not need to expose the full checkpoint to the user.

## Elevated-Risk Path

When a resilience signal is present, the agent should slow down enough to avoid fabrication, hidden failure, false completion, or defensive responses.

The user-facing response should stay concise. The checkpoint is mainly an internal control, not a long explanation.
