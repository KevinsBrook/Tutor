# -*- coding: utf-8 -*-
"""
LightRAG Retriever v4 (Phase 4)
===============================

Built on v3 and adds:
- anchor-guided constrained retrieval (subgraph/path-like constraint)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .lightrag_v3 import LightRAGRetrieverV3
from .lightrag_v2 import LightRAGRetrieverV2


class LightRAGRetrieverV4(LightRAGRetrieverV3):
    """LightRAG retriever v4."""

    name = "lightrag_retriever_v4"

    def _extract_anchors(self, query: str) -> List[str]:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,24}|[\u4e00-\u9fff]{2,8}", query or "")
        stop = {"什么", "怎么", "如何", "为什么", "the", "what", "how", "why"}
        anchors: List[str] = []
        seen = set()
        for token in tokens:
            t = token.lower()
            if t in stop:
                continue
            if token in seen:
                continue
            seen.add(token)
            anchors.append(token)
            if len(anchors) >= 4:
                break
        return anchors

    def _fuse_texts(self, texts: List[str]) -> str:
        seen = set()
        kept = []
        for t in texts:
            normalized = re.sub(r"\s+", " ", (t or "").strip())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            kept.append(t.strip())
        return "\n\n".join(kept)

    async def process(
        self,
        query: str,
        kb_name: str,
        mode: str = "hybrid",
        only_need_context: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Search using v3 + anchor-guided constrained retrieval.
        """
        primary = await super().process(
            query=query,
            kb_name=kb_name,
            mode=mode,
            only_need_context=only_need_context,
            **kwargs,
        )

        enable_constraint = kwargs.get("enable_subgraph_constraint", True)
        anchors = self._extract_anchors(query)
        if not enable_constraint or not anchors:
            primary["provider"] = "lightrag_v4"
            metadata = primary.get("metadata", {})
            metadata.update({"anchors": anchors, "constraint_enabled": bool(enable_constraint)})
            primary["metadata"] = metadata
            return primary

        constrained_query = f"{query}\n关键实体: {'、'.join(anchors)}"
        constrained = await LightRAGRetrieverV2.process(
            self,
            query=constrained_query,
            kb_name=kb_name,
            mode="local",
            only_need_context=only_need_context,
            **kwargs,
        )

        fused = self._fuse_texts(
            [
                primary.get("content", ""),
                constrained.get("content", ""),
            ]
        )

        metadata = primary.get("metadata", {})
        metadata.update(
            {
                "anchors": anchors,
                "constraint_enabled": True,
                "constraint_mode": "local",
            }
        )

        return {
            "query": query,
            "answer": fused,
            "content": fused,
            "mode": mode,
            "provider": "lightrag_v4",
            "metadata": metadata,
        }
