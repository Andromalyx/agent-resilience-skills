"""Integrity checkpoint helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


UNCERTAINTY_MARKERS = ("unknown", "not sure", "maybe", "assume", "guess", "unclear")
FAILURE_MARKERS = ("failed", "error", "timeout", "blocked", "cannot", "can't")
COMPLETION_MARKERS = ("done", "complete", "fixed", "deployed", "resolved", "finished")
VERIFICATION_MARKERS = ("verified", "tested", "confirmed", "passed", "checked")


@dataclass(frozen=True)
class IntegrityCheckpoint:
    """Snapshot of what the agent can honestly claim."""

    known_facts: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    failed_or_blocked: tuple[str, ...] = ()
    completion_claim_requires_verification: bool = False
    recommended_disclosure: str = ""
    next_action: str = ""
    signals: tuple[str, ...] = field(default_factory=tuple)


def run_integrity_checkpoint(text: str, signals: tuple[str, ...] = ()) -> IntegrityCheckpoint:
    """Build an integrity checkpoint from text and detected signals."""
    normalized = text.lower()
    uncertainties = _markers_present(normalized, UNCERTAINTY_MARKERS)
    failed_or_blocked = _markers_present(normalized, FAILURE_MARKERS)
    completion_markers = _markers_present(normalized, COMPLETION_MARKERS)
    verification_markers = _markers_present(normalized, VERIFICATION_MARKERS)
    completion_needs_verification = bool(completion_markers and not verification_markers)

    known_facts = _known_facts(signals, failed_or_blocked, uncertainties)
    disclosure = _recommended_disclosure(
        uncertainties=uncertainties,
        failed_or_blocked=failed_or_blocked,
        completion_needs_verification=completion_needs_verification,
    )

    return IntegrityCheckpoint(
        known_facts=known_facts,
        uncertainties=uncertainties,
        failed_or_blocked=failed_or_blocked,
        completion_claim_requires_verification=completion_needs_verification,
        recommended_disclosure=disclosure,
        next_action=_next_action(signals, completion_needs_verification),
        signals=signals,
    )


def _markers_present(text: str, markers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(marker for marker in markers if marker in text)


def _known_facts(
    signals: tuple[str, ...],
    failed_or_blocked: tuple[str, ...],
    uncertainties: tuple[str, ...],
) -> tuple[str, ...]:
    facts: list[str] = []
    if signals:
        facts.append(f"Detected resilience signals: {', '.join(signals)}.")
    if failed_or_blocked:
        facts.append("A failure or blocker is present.")
    if uncertainties:
        facts.append("The input contains uncertainty markers.")
    return tuple(facts)


def _recommended_disclosure(
    uncertainties: tuple[str, ...],
    failed_or_blocked: tuple[str, ...],
    completion_needs_verification: bool,
) -> str:
    if completion_needs_verification:
        return "Do not claim completion until verification is available."
    if failed_or_blocked:
        return "Disclose the failure or blocker before planning recovery."
    if uncertainties:
        return "Label uncertainty and avoid presenting assumptions as facts."
    return "Proceed normally, while keeping claims evidence-based."


def _next_action(signals: tuple[str, ...], completion_needs_verification: bool) -> str:
    if completion_needs_verification:
        return "Verify completion with the relevant check before saying it is done."
    if "tool_failure" in signals:
        return "Inspect the failure, retry with a changed approach, or use an alternate path."
    if "dishonest_request" in signals:
        return "Refuse misrepresentation and offer a compliant alternative."
    if "conflicting_objectives" in signals:
        return "Frame the tradeoff explicitly before recommending an option."
    if "missing_data" in signals:
        return "Report missing data, analyze available fields, and mark dependent conclusions."
    if "urgency_pressure" in signals:
        return "Prioritize accuracy and state what can be confirmed now."
    if "long_task_pressure" in signals:
        return "Break the work into phases and complete the first useful increment."
    if "user_frustration" in signals:
        return "Acknowledge the issue, correct course, and give a concrete next step."
    if "hallucination_risk" in signals:
        return "Verify the claim, label it as uncertain, or narrow the answer to known facts."
    if "impossible_task" in signals:
        return "State the constraint and offer the closest safe recoverable action."
    if "ambiguity" in signals:
        return "Clarify the missing requirement or proceed with a labeled assumption."
    return "Continue with the requested task."
