"""
Dependency resolution utilities for workflow DAG analysis.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Set

from dwc.ir.spec_schema import WorkflowSpec


class DependencyResolver:
    def adjacency(self, spec: WorkflowSpec) -> Dict[str, Set[str]]:
        graph: Dict[str, Set[str]] = {step.id: set() for step in spec.steps}
        for edge in spec.edges:
            graph.setdefault(edge.source, set()).add(edge.target)
            graph.setdefault(edge.target, set())
        return graph

    def reverse_adjacency(self, spec: WorkflowSpec) -> Dict[str, Set[str]]:
        reverse: Dict[str, Set[str]] = {step.id: set() for step in spec.steps}
        for edge in spec.edges:
            reverse.setdefault(edge.target, set()).add(edge.source)
            reverse.setdefault(edge.source, set())
        return reverse

    def topological_order(self, spec: WorkflowSpec) -> List[str]:
        graph = self.adjacency(spec)
        in_degree: Dict[str, int] = {node: 0 for node in graph}
        for source in graph:
            for target in graph[source]:
                in_degree[target] += 1

        queue = deque(sorted(node for node, degree in in_degree.items() if degree == 0))
        order: List[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for target in sorted(graph[node]):
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    queue.append(target)
        if len(order) != len(graph):
            raise ValueError("Workflow graph contains a cycle and cannot be sorted.")
        return order

    def roots(self, spec: WorkflowSpec) -> List[str]:
        graph = self.adjacency(spec)
        in_degree: Dict[str, int] = {node: 0 for node in graph}
        for source in graph:
            for target in graph[source]:
                in_degree[target] += 1
        return sorted(node for node, degree in in_degree.items() if degree == 0)

    def sinks(self, spec: WorkflowSpec) -> List[str]:
        graph = self.adjacency(spec)
        return sorted(node for node, targets in graph.items() if len(targets) == 0)

    def has_path(self, spec: WorkflowSpec, source: str, target: str) -> bool:
        graph = self.adjacency(spec)
        if source not in graph or target not in graph:
            return False
        queue = deque([source])
        visited: Set[str] = set()
        while queue:
            current = queue.popleft()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            for nxt in graph[current]:
                if nxt not in visited:
                    queue.append(nxt)
        return False

    def find_parallel_groups(self, spec: WorkflowSpec) -> List[List[str]]:
        """
        Detect sibling nodes that can run in parallel.
        Conservative: siblings are grouped only if no path exists between any pair.
        """

        graph = self.adjacency(spec)
        groups: List[List[str]] = []
        for parent, children_set in sorted(graph.items()):
            children = sorted(children_set)
            if len(children) < 2:
                continue

            independent: List[str] = []
            for child in children:
                if all(
                    not self.has_path(spec, child, other)
                    and not self.has_path(spec, other, child)
                    for other in independent
                ):
                    independent.append(child)
            if len(independent) > 1:
                groups.append(independent)
        return groups
