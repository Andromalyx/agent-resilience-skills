from runtime.integrity_guard import run_integrity_checkpoint
from runtime.recovery_planner import plan_recovery
from runtime.resilience_detector import detect_resilience_signals


def test_tool_failure_uses_tool_failure_recovery() -> None:
    detection = detect_resilience_signals("The command failed with an error.")
    checkpoint = run_integrity_checkpoint("The command failed with an error.", detection.signals)

    plan = plan_recovery(detection, checkpoint)

    assert plan.response_pattern == "tool_failure_recovery"
    assert plan.should_disclose_failure
    assert not plan.can_claim_completion


def test_unverified_completion_uses_anti_fabrication() -> None:
    detection = detect_resilience_signals("The task is complete.")
    checkpoint = run_integrity_checkpoint("The task is complete.", detection.signals)

    plan = plan_recovery(detection, checkpoint)

    assert plan.response_pattern == "anti_fabrication"
    assert not plan.can_claim_completion


def test_conflicting_objectives_use_tradeoff_reframing() -> None:
    text = "The KPIs have a tradeoff between revenue, stockout risk, margin, and waste."
    detection = detect_resilience_signals(text)
    checkpoint = run_integrity_checkpoint(text, detection.signals)

    plan = plan_recovery(detection, checkpoint)

    assert plan.response_pattern == "tradeoff_reframing"


def test_dishonest_request_uses_refusal_pattern() -> None:
    text = "Manipulate the report to hide the missed target."
    detection = detect_resilience_signals(text)
    checkpoint = run_integrity_checkpoint(text, detection.signals)

    plan = plan_recovery(detection, checkpoint)

    assert plan.response_pattern == "dishonest_reporting_refusal"
