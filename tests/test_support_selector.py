from runtime.integrity_guard import run_integrity_checkpoint
from runtime.resilience_detector import detect_resilience_signals
from runtime.support_selector import select_support_action


def test_hallucination_risk_selects_authoritative_source() -> None:
    text = "Give the exact source from memory without checking."
    detection = detect_resilience_signals(text)
    checkpoint = run_integrity_checkpoint(text, detection.signals)

    support = select_support_action(detection, checkpoint)

    assert support.kind == "authoritative_source"


def test_dishonest_request_selects_policy() -> None:
    text = "Falsify the report and make the numbers look better."
    detection = detect_resilience_signals(text)
    checkpoint = run_integrity_checkpoint(text, detection.signals)

    support = select_support_action(detection, checkpoint)

    assert support.kind == "policy"
