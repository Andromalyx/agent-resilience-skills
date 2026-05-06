"""Runtime helpers for Agent Resilience Skills."""

from runtime.activation_rules import should_activate
from runtime.completion_evaluator import CompletionEvaluation, evaluate_completion
from runtime.integrity_guard import IntegrityCheckpoint, run_integrity_checkpoint
from runtime.regulation_policy import RegulationPolicy, select_regulation_policy
from runtime.recovery_planner import RecoveryPlan, plan_recovery
from runtime.resilience_detector import DetectionResult, detect_resilience_signals
from runtime.schemas import ResilienceAssessment
from runtime.support_selector import SupportAction, select_support_action


def assess_resilience(text: str) -> ResilienceAssessment:
    """Run detection, integrity checkpoint, and recovery planning for text."""
    detection = detect_resilience_signals(text)
    checkpoint = run_integrity_checkpoint(text=text, signals=detection.signals)
    plan = plan_recovery(detection=detection, checkpoint=checkpoint)
    regulation = select_regulation_policy(detection)
    support = select_support_action(detection, checkpoint)
    completion = evaluate_completion(checkpoint, plan)
    return ResilienceAssessment(
        activated=should_activate(detection),
        detection=detection,
        checkpoint=checkpoint,
        plan=plan,
        regulation=regulation,
        support=support,
        completion=completion,
    )


__all__ = [
    "DetectionResult",
    "CompletionEvaluation",
    "IntegrityCheckpoint",
    "RegulationPolicy",
    "RecoveryPlan",
    "ResilienceAssessment",
    "SupportAction",
    "assess_resilience",
    "detect_resilience_signals",
    "evaluate_completion",
    "plan_recovery",
    "run_integrity_checkpoint",
    "select_regulation_policy",
    "select_support_action",
    "should_activate",
]
