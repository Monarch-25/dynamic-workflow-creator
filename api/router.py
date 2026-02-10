"""
FastAPI router for Dynamic Workflow Compiler.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from dwc.main import DynamicWorkflowCompiler

try:  # Optional runtime dependency
    from fastapi import APIRouter, HTTPException
except ImportError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    HTTPException = RuntimeError  # type: ignore[assignment]


class CompileRequest(BaseModel):
    requirements: str
    workflow_name: Optional[str] = None
    approved_plan: Optional[str] = None
    intent_summary: Optional[str] = None
    execute: bool = True
    max_tool_iterations: int = Field(default=4, ge=1, le=20)
    initial_state: Dict[str, Any] = Field(default_factory=dict)
    session_mode: str = Field(default="isolated", pattern="^(isolated|shared)$")
    session_id: Optional[str] = None
    dwc_root: str = ".dwc"


class CompileResponse(BaseModel):
    artifact: Dict[str, Any]


if APIRouter is not None:
    router = APIRouter(prefix="/dwc", tags=["dwc"])

    @router.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @router.post("/compile", response_model=CompileResponse)
    def compile_workflow(payload: CompileRequest) -> CompileResponse:
        try:
            compiler = DynamicWorkflowCompiler(
                session_mode=payload.session_mode,
                session_id=payload.session_id,
                dwc_root=payload.dwc_root,
            )
            artifact = compiler.compile_from_nl(
                requirements_text=payload.requirements,
                workflow_name=payload.workflow_name,
                approved_plan=payload.approved_plan,
                intent_summary=payload.intent_summary,
                execute=payload.execute,
                max_tool_iterations=payload.max_tool_iterations,
                initial_state=payload.initial_state,
            )
            response = (
                artifact.model_dump()
                if hasattr(artifact, "model_dump")
                else artifact.dict()
            )
            return CompileResponse(artifact=response)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
else:
    router = None
