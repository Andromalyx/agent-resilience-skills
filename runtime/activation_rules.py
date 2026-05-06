"""Activation decisions for resilience behavior."""

from __future__ import annotations

from runtime.resilience_detector import DetectionResult


HIGH_PRIORITY_SIGNALS = {
    "tool_failure",
    "user_frustration",
    "hallucination_risk",
    "impossible_task",
}


def should_activate(detection: DetectionResult) -> bool:
    """Return whether resilience handling should activate."""
    if detection.stress_level in {"medium", "high"}:
        return True
    if any(signal in HIGH_PRIORITY_SIGNALS for signal in detection.signals):
        return True
    return len(detection.signals) >= 1
