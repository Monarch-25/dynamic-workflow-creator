"""
Planning-stage service for requirement interpretation and plan mode.
"""

from __future__ import annotations

import sys
from typing import Optional, Tuple

from dwc.agents.planner_agent import PlanResult, PlannerAgent


class PlanningService:
    def __init__(self, planner: PlannerAgent) -> None:
        self.planner = planner

    def run_plan_mode(
        self, initial_requirements: Optional[str] = None, max_iterations: int = 6
    ) -> PlanResult:
        if not sys.stdin.isatty():
            raise RuntimeError(
                "Plan mode is interactive. Provide --requirements in non-interactive runs."
            )

        requirements_text = (initial_requirements or "").strip()
        if not requirements_text:
            requirements_text = input("Describe the workflow you want to build:\n> ").strip()
        if not requirements_text:
            raise ValueError("Requirements cannot be empty.")

        feedback = ""
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            plan = self.planner.propose_plan(requirements_text, feedback)
            print("\nProposed Plan\n")
            print(plan)
            decision = input("\nApprove plan? [y]es / [r]efine / [q]uit\n> ").strip().lower()

            if decision in ("y", "yes"):
                intent_summary = self.planner.capture_intent(requirements_text, plan)
                return PlanResult(
                    requirements_text=requirements_text,
                    proposed_plan=plan,
                    intent_summary=intent_summary,
                    iterations=iteration,
                )
            if decision in ("q", "quit"):
                raise RuntimeError("Plan mode canceled by user.")

            refinement = input("Enter refinements for the next plan revision:\n> ").strip()
            feedback = refinement or "Please simplify and improve robustness."

        raise RuntimeError("Plan mode exceeded maximum iterations without approval.")

    def resolve_plan(
        self,
        *,
        requirements_text: str,
        approved_plan: Optional[str] = None,
        intent_summary: Optional[str] = None,
    ) -> Tuple[str, str]:
        resolved_plan = approved_plan or self.planner.propose_plan(requirements_text)
        resolved_intent = intent_summary or self.planner.capture_intent(
            requirements_text, resolved_plan
        )
        return resolved_plan, resolved_intent

    @staticmethod
    def compose_current_task_description(
        *,
        requirements_text: str,
        approved_plan: str,
        intent_summary: str,
    ) -> str:
        return (
            "User Requirements:\n"
            f"{requirements_text.strip()}\n\n"
            "Approved Plan:\n"
            f"{approved_plan.strip()}\n\n"
            "Intent Summary:\n"
            f"{intent_summary.strip()}\n"
        )
