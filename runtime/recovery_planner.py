"""Recovery plan generation for resilience events."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.integrity_guard import IntegrityCheckpoint
from runtime.resilience_detector import DetectionResult


@dataclass(frozen=True)
class RecoveryPlan:
    """A compact plan for the agent's next response."""

    response_pattern: str
    next_action: str
    should_disclose_failure: bool = False
    should_disclose_uncertainty: bool = False
    can_claim_completion: bool = True


def plan_recovery(detection: DetectionResult, checkpoint: IntegrityCheckpoint) -> RecoveryPlan:
    """Choose a response pattern and next action from detection and checkpoint data."""
    signals = set(detection.signals)

    if checkpoint.completion_claim_requires_verification:
        return RecoveryPlan(
            response_pattern="anti_fabrication",
            next_action=checkpoint.next_action,
            should_disclose_uncertainty=True,
            can_claim_completion=False,
        )

    if "dishonest_request" in signals:
        return RecoveryPlan(
            response_pattern="dishonest_reporting_refusal",
            next_action=checkpoint.next_action,
            should_disclose_uncertainty=False,
            can_claim_completion=False,
        )

    if "tool_failure" in signals:
        return RecoveryPlan(
            response_pattern="tool_failure_recovery",
            next_action=checkpoint.next_action,
            should_disclose_failure=True,
            can_claim_completion=False,
        )

    if "conflicting_objectives" in signals:
        return RecoveryPlan(
            response_pattern="tradeoff_reframing",
            next_action=checkpoint.next_action,
            should_disclose_uncertainty=True,
            can_claim_completion=False,
        )

    if "missing_data" in signals:
        return RecoveryPlan(
            response_pattern="partial_analysis_recovery",
            next_action=checkpoint.next_action,
            should_disclose_uncertainty=True,
            can_claim_completion=False,
        )

    if "urgency_pressure" in signals:
        if checkpoint.uncertainties or "ambiguity" in signals:
            return RecoveryPlan(
                response_pattern="uncertainty_disclosure",
                next_action=checkpoint.next_action,
                should_disclose_uncertainty=True,
                can_claim_completion=False,
            )
        return RecoveryPlan(
            response_pattern="calm_recovery",
            next_action=checkpoint.next_action,
            should_disclose_uncertainty=bool(checkpoint.uncertainties),
            can_claim_completion=False,
        )

    if "long_task_pressure" in signals:
        return RecoveryPlan(
            response_pattern="incremental_recovery",
            next_action=checkpoint.next_action,
            can_claim_completion=False,
        )

    if "user_frustration" in signals:
        return RecoveryPlan(
            response_pattern="user_frustration_repair",
            next_action=checkpoint.next_action,
            should_disclose_failure=bool(checkpoint.failed_or_blocked),
            can_claim_completion=False,
        )

    if "hallucination_risk" in signals or checkpoint.uncertainties:
        return RecoveryPlan(
            response_pattern="uncertainty_disclosure",
            next_action=checkpoint.next_action,
            should_disclose_uncertainty=True,
            can_claim_completion=False,
        )

    if "impossible_task" in signals:
        return RecoveryPlan(
            response_pattern="refusal_and_recovery",
            next_action=checkpoint.next_action,
            should_disclose_uncertainty=True,
            can_claim_completion=False,
        )

    if signals:
        return RecoveryPlan(
            response_pattern="calm_recovery",
            next_action=checkpoint.next_action,
            can_claim_completion=False,
        )

    return RecoveryPlan(
        response_pattern="normal",
        next_action=checkpoint.next_action,
        can_claim_completion=True,
    )
