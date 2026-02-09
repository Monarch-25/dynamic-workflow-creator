"""
Lightweight local vector store for workflow memory.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class VectorRecord(BaseModel):
    key: str
    text: str
    vector: List[float]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LocalVectorStore:
    """
    Deterministic embedding store without external ML dependencies.
    """

    def __init__(self, path: str = ".dwc/memory/vector_store.jsonl", dim: int = 64):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dim = dim

    def add(
        self, text: str, *, key: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        doc_key = key or hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        vector = self._embed(text)
        record = VectorRecord(
            key=doc_key, text=text, vector=vector, metadata=metadata or {}
        )
        payload = record.model_dump() if hasattr(record, "model_dump") else record.dict()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return doc_key

    def search(
        self, query: str, *, top_k: int = 5, min_score: float = -1.0
    ) -> List[Tuple[float, VectorRecord]]:
        query_vec = self._embed(query)
        scored: List[Tuple[float, VectorRecord]] = []
        for record in self._iter_records():
            score = self._cosine_similarity(query_vec, record.vector)
            if score >= min_score:
                scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[:top_k]

    def _iter_records(self) -> List[VectorRecord]:
        if not self.path.exists():
            return []
        rows: List[VectorRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(VectorRecord(**json.loads(line)))
        return rows

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dim
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        for token in tokens:
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            index = digest[0] % self.dim
            sign = 1.0 if digest[1] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        if len(a) != len(b):
            return -1.0
        return float(sum(x * y for x, y in zip(a, b)))
