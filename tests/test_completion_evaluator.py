from runtime.completion_evaluator import evaluate_completion
from runtime.integrity_guard import run_integrity_checkpoint
from runtime.recovery_planner import plan_recovery
from runtime.resilience_detector import detect_resilience_signals


def test_unverified_completion_cannot_be_claimed() -> None:
    text = "The deployment is done."
    detection = detect_resilience_signals(text)
    checkpoint = run_integrity_checkpoint(text, detection.signals)
    plan = plan_recovery(detection, checkpoint)

    completion = evaluate_completion(checkpoint, plan)

    assert not completion.can_claim_complete
    assert "unverified completion claim" in completion.reason


def test_verified_normal_plan_can_claim_completion_when_allowed() -> None:
    text = "Summarize the known facts."
    detection = detect_resilience_signals(text)
    checkpoint = run_integrity_checkpoint(text, detection.signals)
    plan = plan_recovery(detection, checkpoint)

    completion = evaluate_completion(checkpoint, plan, verified=True)

    assert completion.can_claim_complete
