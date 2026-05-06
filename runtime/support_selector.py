"""Support action selection for resilience recovery."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.integrity_guard import IntegrityCheckpoint
from runtime.resilience_detector import DetectionResult


@dataclass(frozen=True)
class SupportAction:
    """Recommended support route for the next honest action."""

    kind: str
    reason: str


def select_support_action(
    detection: DetectionResult,
    checkpoint: IntegrityCheckpoint,
) -> SupportAction:
    """Choose whether the agent should use tools, ask, cite, calculate, or escalate."""
    signals = set(detection.signals)

    if "dishonest_request" in signals:
        return SupportAction("policy", "Dishonest or misleading reporting requires refusal and compliant alternative.")
    if "tool_failure" in signals:
        return SupportAction("alternate_tool_or_retry", "A failed tool needs changed retry parameters or an alternate route.")
    if "hallucination_risk" in signals:
        return SupportAction("authoritative_source", "The claim needs verification before being stated as fact.")
    if "missing_data" in signals:
        return SupportAction("data_inspection", "Missing fields should be identified before analysis continues.")
    if "conflicting_objectives" in signals:
        return SupportAction("tradeoff_analysis", "Conflicting objectives should be compared explicitly.")
    if "impossible_task" in signals:
        return SupportAction("clarify_or_escalate", "The constraint may require user input, safe alternative, or escalation.")
    if checkpoint.uncertainties:
        return SupportAction("targeted_clarification", "A narrow clarification can resolve blocking uncertainty.")
    return SupportAction("none", "No additional support action is required.")
