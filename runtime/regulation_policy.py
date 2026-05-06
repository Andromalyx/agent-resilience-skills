"""Tone and response regulation for resilience events."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.resilience_detector import DetectionResult


@dataclass(frozen=True)
class RegulationPolicy:
    """User-facing response style constraints."""

    tone: str
    max_detail: str
    avoid: tuple[str, ...]
    required: tuple[str, ...]


def select_regulation_policy(detection: DetectionResult) -> RegulationPolicy:
    """Select a regulated response style based on stress level and signals."""
    if detection.stress_level == "low":
        return RegulationPolicy(
            tone="normal",
            max_detail="normal",
            avoid=("unsupported claims",),
            required=("answer the request",),
        )

    if "user_frustration" in detection.signals:
        return RegulationPolicy(
            tone="calm and non-defensive",
            max_detail="concise",
            avoid=("argument", "blame", "exaggerated apology", "overconfidence"),
            required=("acknowledge issue", "correct course", "give next action"),
        )

    return RegulationPolicy(
        tone="calm and direct",
        max_detail="focused",
        avoid=("fabrication", "hidden failure", "rushed certainty", "overpromising"),
        required=("state verified facts", "state uncertainty when relevant", "give next action"),
    )
