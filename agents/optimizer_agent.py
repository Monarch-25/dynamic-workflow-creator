"""
Optimizer agent wrapper over IR optimization passes.
"""

from __future__ import annotations

from typing import Optional

from dwc.compiler.optimization_passes import Optimizer
from dwc.ir.spec_schema import WorkflowSpec


class OptimizerAgent:
    def __init__(self, optimizer: Optional[Optimizer] = None) -> None:
        self.optimizer = optimizer or Optimizer()

    def optimize(self, spec: WorkflowSpec) -> WorkflowSpec:
        return self.optimizer.optimize(spec)
