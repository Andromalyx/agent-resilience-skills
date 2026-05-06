"""Rule-based resilience signal detection."""

from __future__ import annotations

from dataclasses import dataclass, field


SIGNAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tool_failure": (
        "failed",
        "failure",
        "timeout",
        "timed out",
        "error",
        "exception",
        "blocked",
        "permission denied",
        "network",
        "unavailable",
    ),
    "user_frustration": (
        "angry",
        "frustrated",
        "upset",
        "wrong",
        "you said",
        "not working",
        "still fails",
        "unacceptable",
    ),
    "ambiguity": (
        "ambiguous",
        "unclear",
        "not sure",
        "maybe",
        "conflicting",
        "unknown",
        "missing context",
    ),
    "missing_data": (
        "missing data",
        "missing field",
        "missing fields",
        "incomplete data",
        "no data",
        "data is missing",
    ),
    "urgency_pressure": (
        "urgent",
        "right now",
        "instant",
        "immediately",
        "asap",
        "need it now",
        "fast",
    ),
    "conflicting_objectives": (
        "conflicting kpi",
        "conflicting kpis",
        "tradeoff",
        "trade off",
        "speed versus accuracy",
        "revenue",
        "stockout",
        "margin",
        "waste",
    ),
    "hallucination_risk": (
        "from memory",
        "guess",
        "exact",
        "cite",
        "source",
        "prove",
        "without checking",
        "assume",
    ),
    "impossible_task": (
        "impossible",
        "can't",
        "cannot",
        "no access",
        "unavailable",
        "not possible",
    ),
    "dishonest_request": (
        "manipulate",
        "misrepresent",
        "hide the",
        "make the report look",
        "fake",
        "falsify",
        "dishonest",
    ),
    "long_task_pressure": (
        "long task",
        "large task",
        "complex task",
        "many steps",
        "rush",
        "shallow",
    ),
    "completion_claim": (
        "done",
        "complete",
        "fixed",
        "deployed",
        "resolved",
        "finished",
    ),
}


@dataclass(frozen=True)
class DetectionResult:
    """Detected resilience signals and plain-language evidence."""

    signals: tuple[str, ...] = ()
    evidence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    stress_level: str = "low"

    @property
    def activated(self) -> bool:
        return bool(self.signals)


def detect_resilience_signals(text: str) -> DetectionResult:
    """Detect resilience activation signals in free-form text.

    This intentionally starts as a transparent keyword detector. Production systems
    can replace or augment it with model-based classification while preserving the
    same output shape.
    """
    normalized = text.lower()
    evidence: dict[str, tuple[str, ...]] = {}

    for signal, keywords in SIGNAL_KEYWORDS.items():
        matches = tuple(keyword for keyword in keywords if keyword in normalized)
        if matches:
            evidence[signal] = matches

    signals = tuple(evidence)
    return DetectionResult(signals=signals, evidence=evidence, stress_level=_stress_level(signals))


def _stress_level(signals: tuple[str, ...]) -> str:
    if not signals:
        return "low"
    high_stress = {
        "tool_failure",
        "user_frustration",
        "hallucination_risk",
        "impossible_task",
        "dishonest_request",
        "completion_claim",
    }
    if any(signal in high_stress for signal in signals) or len(signals) >= 3:
        return "high"
    return "medium"
