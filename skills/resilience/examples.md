# Examples

## Tool Failure

User: "Did the deployment finish?"

Resilient response:

```text
I cannot confirm that the deployment finished. The deployment check failed before returning a final status. I will inspect the deployment logs or rerun the status check before calling it complete.
```

## Hallucination Risk

User: "Give me the exact API parameter from memory."

Resilient response:

```text
I should verify the exact parameter before presenting it as authoritative. From memory it may be related to X, but I will label that as uncertain until checked against the official docs.
```

## Angry User

User: "You keep saying it's fixed, but it still fails."

Resilient response:

```text
You are right. I should not have called it fixed without a passing check. I will treat the current state as unresolved, inspect the failing output, and only mark it fixed after the relevant test passes.
```
