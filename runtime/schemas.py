"""Shared runtime schemas."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.completion_evaluator import CompletionEvaluation
from runtime.integrity_guard import IntegrityCheckpoint
from runtime.regulation_policy import RegulationPolicy
from runtime.recovery_planner import RecoveryPlan
from runtime.resilience_detector import DetectionResult
from runtime.support_selector import SupportAction


@dataclass(frozen=True)
class ResilienceAssessment:
    """Full resilience assessment result."""

    activated: bool
    detection: DetectionResult
    checkpoint: IntegrityCheckpoint
    plan: RecoveryPlan
    regulation: RegulationPolicy
    support: SupportAction
    completion: CompletionEvaluation
