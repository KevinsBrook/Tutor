# -*- coding: utf-8 -*-
"""
LightRAG Retriever v1 (Phase 1)
===============================

Phase-1 optimization:
- cold-start optimization via shared runtime cache
"""

from pathlib import Path
from typing import Any, Dict, Optional

from ..base import BaseComponent
from ..lightrag_runtime_v1 import LightRAGRuntimeV1


class LightRAGRetrieverV1(BaseComponent):
    """LightRAG retriever v1."""

    name = "lightrag_retriever_v1"

    def __init__(self, kb_base_dir: Optional[str] = None):
        super().__init__()
        self.kb_base_dir = kb_base_dir or str(
            Path(__file__).resolve().parent.parent.parent.parent.parent.parent
            / "data"
            / "knowledge_bases"
        )

    def _working_dir(self, kb_name: str) -> str:
        return str(Path(self.kb_base_dir) / kb_name / "rag_storage")

    async def process(
        self,
        query: str,
        kb_name: str,
        mode: str = "hybrid",
        only_need_context: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Search using LightRAG retrieval (v1)."""
        self.logger.info(f"LightRAG-v1 search ({mode}) in {kb_name}: {query[:50]}...")

        working_dir = self._working_dir(kb_name)
        from src.logging.adapters import LightRAGLogContext

        with LightRAGLogContext(scene="LightRAG-Search-v1"):
            rag = LightRAGRuntimeV1.get_or_create(working_dir)
            await LightRAGRuntimeV1.ensure_initialized(working_dir, rag)

            from lightrag import QueryParam

            query_param = QueryParam(mode=mode, only_need_context=only_need_context)
            answer = await rag.aquery(query, param=query_param)
            answer_str = answer if isinstance(answer, str) else str(answer)

            return {
                "query": query,
                "answer": answer_str,
                "content": answer_str,
                "mode": mode,
                "provider": "lightrag_v1",
            }
