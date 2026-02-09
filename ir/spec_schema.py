"""
Typed intermediate representation for Dynamic Workflow Compiler (DWC).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

try:  # pydantic v2
    from pydantic import ConfigDict
except ImportError:  # pydantic v1
    ConfigDict = None  # type: ignore[assignment]


class StrictModel(BaseModel):
    """Base model that rejects undeclared fields."""

    class Config:
        extra = "forbid"


if ConfigDict is not None:
    StrictModel.model_config = ConfigDict(extra="forbid")  # type: ignore[attr-defined]


class InputSpec(StrictModel):
    id: str
    name: str
    data_type: str
    required: bool = True
    description: Optional[str] = None
    default: Optional[Any] = None


class OutputSpec(StrictModel):
    id: str
    name: str
    data_type: str
    source_step: Optional[str] = None
    description: Optional[str] = None


class ConstraintSpec(StrictModel):
    id: str
    kind: str
    expression: str
    severity: Literal["low", "medium", "high"] = "medium"


class RetryPolicy(StrictModel):
    max_retries: int = Field(default=2, ge=0, le=10)
    backoff_strategy: Literal["fixed", "exponential"] = "exponential"
    initial_delay_seconds: float = Field(default=1.0, gt=0)
    max_delay_seconds: float = Field(default=30.0, gt=0)


class StepSpec(StrictModel):
    id: str
    type: Literal["llm", "tool", "condition", "transform"]
    config: Dict[str, Any] = Field(default_factory=dict)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_seconds: int = Field(default=120, ge=1)


class EdgeSpec(StrictModel):
    source: str
    target: str
    condition: Optional[str] = None


class WorkflowSpec(StrictModel):
    version: str = "1.0.0"
    name: str
    description: str
    inputs: List[InputSpec] = Field(default_factory=list)
    outputs: List[OutputSpec] = Field(default_factory=list)
    steps: List[StepSpec] = Field(default_factory=list)
    edges: List[EdgeSpec] = Field(default_factory=list)
    constraints: Optional[List[ConstraintSpec]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def step_ids(self) -> List[str]:
        return [step.id for step in self.steps]

    def step_map(self) -> Dict[str, StepSpec]:
        return {step.id: step for step in self.steps}

    def edge_map(self) -> Dict[str, List[EdgeSpec]]:
        mapping: Dict[str, List[EdgeSpec]] = {}
        for edge in self.edges:
            mapping.setdefault(edge.source, []).append(edge)
        return mapping

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(model_dump_compat(self), indent=indent, sort_keys=True)


def model_dump_compat(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


def model_copy_compat(model: BaseModel, deep: bool = False) -> BaseModel:
    if hasattr(model, "model_copy"):
        return model.model_copy(deep=deep)  # type: ignore[attr-defined]
    return model.copy(deep=deep)


def model_validate_json_compat(raw: str) -> WorkflowSpec:
    if hasattr(WorkflowSpec, "model_validate_json"):
        return WorkflowSpec.model_validate_json(raw)  # type: ignore[attr-defined]
    return WorkflowSpec.parse_raw(raw)
