"""
Planning-stage service for requirement interpretation and plan mode.
"""

from __future__ import annotations

import sys
from typing import Optional, Tuple

from dwc.agents.planner_agent import PlanResult, PlannerAgent
from dwc.memory.agent_todo_board import AgentTodoBoard


class PlanningService:
    def __init__(
        self,
        planner: PlannerAgent,
        todo_board: Optional[AgentTodoBoard] = None,
    ) -> None:
        self.planner = planner
        self.todo_board = todo_board

    def run_plan_mode(
        self, initial_requirements: Optional[str] = None, max_iterations: int = 6
    ) -> PlanResult:
        if self.todo_board is not None:
            self.todo_board.start("planner_agent", "interactive_plan", "Collecting requirements.")
        if not sys.stdin.isatty():
            if self.todo_board is not None:
                self.todo_board.fail(
                    "planner_agent",
                    "interactive_plan",
                    "Plan mode requires interactive terminal.",
                )
            raise RuntimeError(
                "Plan mode is interactive. Provide --requirements in non-interactive runs."
            )

        requirements_text = (initial_requirements or "").strip()
        if not requirements_text:
            requirements_text = input("Describe the workflow you want to build:\n> ").strip()
        if not requirements_text:
            if self.todo_board is not None:
                self.todo_board.fail(
                    "planner_agent", "interactive_plan", "Requirements cannot be empty."
                )
            raise ValueError("Requirements cannot be empty.")

        feedback = ""
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            if self.todo_board is not None:
                self.todo_board.add_check(
                    "planner_agent",
                    "interactive_plan",
                    f"Iteration {iteration}: proposing plan draft.",
                )
            plan = self.planner.propose_plan(requirements_text, feedback)
            print("\nProposed Plan\n")
            print(plan)
            decision = input("\nApprove plan? [y]es / [r]efine / [q]uit\n> ").strip().lower()

            if decision in ("y", "yes"):
                if self.todo_board is not None:
                    self.todo_board.start(
                        "planner_agent", "capture_intent", "Capturing intent summary."
                    )
                intent_summary = self.planner.capture_intent(requirements_text, plan)
                if self.todo_board is not None:
                    self.todo_board.complete(
                        "planner_agent",
                        "capture_intent",
                        "Intent summary ready.",
                    )
                    self.todo_board.complete(
                        "planner_agent",
                        "interactive_plan",
                        f"Approved in {iteration} iteration(s).",
                    )
                return PlanResult(
                    requirements_text=requirements_text,
                    proposed_plan=plan,
                    intent_summary=intent_summary,
                    iterations=iteration,
                )
            if decision in ("q", "quit"):
                if self.todo_board is not None:
                    self.todo_board.fail(
                        "planner_agent", "interactive_plan", "Canceled by user."
                    )
                raise RuntimeError("Plan mode canceled by user.")

            refinement = input("Enter refinements for the next plan revision:\n> ").strip()
            feedback = refinement or "Please simplify and improve robustness."
            if self.todo_board is not None:
                self.todo_board.add_check(
                    "planner_agent",
                    "interactive_plan",
                    f"Refinement captured: {feedback[:120]}",
                )

        if self.todo_board is not None:
            self.todo_board.fail(
                "planner_agent",
                "interactive_plan",
                "Exceeded maximum plan iterations.",
            )
        raise RuntimeError("Plan mode exceeded maximum iterations without approval.")

    def resolve_plan(
        self,
        *,
        requirements_text: str,
        approved_plan: Optional[str] = None,
        intent_summary: Optional[str] = None,
    ) -> Tuple[str, str]:
        if self.todo_board is not None:
            self.todo_board.start("planner_agent", "resolve_plan", "Resolving approved plan.")
        if approved_plan:
            resolved_plan = approved_plan
            if self.todo_board is not None:
                self.todo_board.complete(
                    "planner_agent", "resolve_plan", "Using caller-provided approved plan."
                )
        else:
            resolved_plan = self.planner.propose_plan(requirements_text)
            if self.todo_board is not None:
                self.todo_board.complete(
                    "planner_agent", "resolve_plan", "Generated approved plan."
                )

        if self.todo_board is not None:
            self.todo_board.start("planner_agent", "capture_intent", "Resolving intent summary.")
        if intent_summary:
            resolved_intent = intent_summary
            if self.todo_board is not None:
                self.todo_board.complete(
                    "planner_agent",
                    "capture_intent",
                    "Using caller-provided intent summary.",
                )
        else:
            resolved_intent = self.planner.capture_intent(requirements_text, resolved_plan)
            if self.todo_board is not None:
                self.todo_board.complete(
                    "planner_agent", "capture_intent", "Generated intent summary."
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
