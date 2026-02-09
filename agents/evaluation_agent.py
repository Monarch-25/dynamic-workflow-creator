"""
Evaluation agent for deciding workflow stability.
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field

from dwc.runtime.executor import ExecutionReport


class StabilityReport(BaseModel):
    stable: bool
    reason: str
    metrics: Dict[str, float] = Field(default_factory=dict)


class EvaluationAgent:
    def evaluate(
        self,
        reports: List[ExecutionReport],
        *,
        min_success_streak: int = 1,
        max_latency_ms: int = 60000,
    ) -> StabilityReport:
        if not reports:
            return StabilityReport(
                stable=False,
                reason="No execution reports available.",
                metrics={},
            )

        success_flags = [report.success for report in reports]
        success_count = sum(1 for flag in success_flags if flag)
        streak = 0
        for flag in reversed(success_flags):
            if flag:
                streak += 1
            else:
                break

        latest = reports[-1]
        avg_latency = sum(report.latency_ms for report in reports) / float(len(reports))
        stable = bool(
            latest.success and streak >= min_success_streak and latest.latency_ms <= max_latency_ms
        )
        reason = "Stable workflow artifact." if stable else "Workflow requires further refinement."

        return StabilityReport(
            stable=stable,
            reason=reason,
            metrics={
                "total_runs": float(len(reports)),
                "success_count": float(success_count),
                "success_ratio": float(success_count / len(reports)),
                "latest_latency_ms": float(latest.latency_ms),
                "avg_latency_ms": float(avg_latency),
                "success_streak": float(streak),
            },
        )
