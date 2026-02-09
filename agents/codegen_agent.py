"""
Code generation agent for LangGraph scripts.
"""

from __future__ import annotations

from typing import Optional

from dwc.compiler.langgraph_codegen import CodegenResult, LangGraphCodeGenerator
from dwc.ir.spec_schema import WorkflowSpec


class CodegenAgent:
    def __init__(self, generator: Optional[LangGraphCodeGenerator] = None) -> None:
        self.generator = generator or LangGraphCodeGenerator()

    def generate(self, spec: WorkflowSpec) -> CodegenResult:
        return self.generator.generate(spec)
