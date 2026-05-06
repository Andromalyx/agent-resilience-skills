from runtime.activation_rules import should_activate
from runtime.resilience_detector import DetectionResult, detect_resilience_signals


def test_detects_tool_failure_signal() -> None:
    result = detect_resilience_signals("The tool timed out with a network error.")

    assert "tool_failure" in result.signals
    assert result.stress_level == "high"
    assert should_activate(result)


def test_no_signal_does_not_activate() -> None:
    result = DetectionResult()

    assert not should_activate(result)


def test_detects_medium_urgency_pressure() -> None:
    result = detect_resilience_signals("I need an instant answer right now.")

    assert "urgency_pressure" in result.signals
    assert result.stress_level == "medium"
    assert should_activate(result)
