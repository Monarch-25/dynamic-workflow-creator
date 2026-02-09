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
    execute: bool = True
    max_reflections: int = Field(default=5, ge=1, le=20)
    initial_state: Dict[str, Any] = Field(default_factory=dict)


class CompileResponse(BaseModel):
    artifact: Dict[str, Any]


if APIRouter is not None:
    router = APIRouter(prefix="/dwc", tags=["dwc"])
    compiler = DynamicWorkflowCompiler()

    @router.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @router.post("/compile", response_model=CompileResponse)
    def compile_workflow(payload: CompileRequest) -> CompileResponse:
        try:
            artifact = compiler.compile_from_nl(
                requirements_text=payload.requirements,
                workflow_name=payload.workflow_name,
                execute=payload.execute,
                max_reflections=payload.max_reflections,
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
