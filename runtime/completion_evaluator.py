"""Completion evaluation for resilience workflows."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.integrity_guard import IntegrityCheckpoint
from runtime.recovery_planner import RecoveryPlan


@dataclass(frozen=True)
class CompletionEvaluation:
    """Whether the agent may honestly claim completion."""

    can_claim_complete: bool
    reason: str
    next_verification_step: str


def evaluate_completion(
    checkpoint: IntegrityCheckpoint,
    plan: RecoveryPlan,
    verified: bool = False,
) -> CompletionEvaluation:
    """Evaluate whether completion language is allowed."""
    if verified and plan.can_claim_completion and not checkpoint.completion_claim_requires_verification:
        return CompletionEvaluation(True, "Completion was verified.", "")

    if checkpoint.completion_claim_requires_verification:
        return CompletionEvaluation(
            False,
            "The input contains an unverified completion claim.",
            checkpoint.next_action,
        )

    if not plan.can_claim_completion:
        return CompletionEvaluation(
            False,
            "The selected recovery pattern requires disclosure or follow-up before completion.",
            checkpoint.next_action,
        )

    return CompletionEvaluation(
        False,
        "Completion has not been verified.",
        "Run the relevant verification check before claiming completion.",
    )
