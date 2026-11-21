# Contributing

Thanks for improving Agent Resilience Skills.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Contribution Guidelines

- Keep behavior calm, honest, and task-focused.
- Prefer small, reviewable changes.
- Add tests for runtime behavior changes.
- Avoid adding platform-specific assumptions to the canonical skill.
- Keep examples realistic and free of unverifiable claims.

## Documentation Changes

When changing the skill, update the matching adapter or implementation guide if the behavior affects integrations.


## Finance engine: one source, one vendored copy

`runtime/finance/` is the source of truth. The FP&A skill ships a copy in
`skills/fpa/scripts/fpa_engine/` so it works when installed on its own. After any change
to `runtime/finance/`, run `python scripts/sync_skill_engine.py`; the test suite fails if
the copy drifts.
