# -*- coding: utf-8 -*-
"""
LightRAG Retriever v2 (Phase 2)
===============================

Built on v1 retriever.
Phase-2 keeps retrieval path stable and tags provider as lightrag_v2.
"""

from typing import Any, Dict

from .lightrag_v1 import LightRAGRetrieverV1


class LightRAGRetrieverV2(LightRAGRetrieverV1):
    """LightRAG retriever v2."""

    name = "lightrag_retriever_v2"

    async def process(
        self,
        query: str,
        kb_name: str,
        mode: str = "hybrid",
        only_need_context: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        result = await super().process(
            query=query,
            kb_name=kb_name,
            mode=mode,
            only_need_context=only_need_context,
            **kwargs,
        )
        result["provider"] = "lightrag_v2"
        return result
