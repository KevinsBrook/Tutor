# -*- coding: utf-8 -*-
"""
LightRAG Retriever v3 (Phase 3)
===============================

Built on v2 retriever and adds phase-3 retrieval strategies:
- query mode auto-routing
- lightweight query rewrite
- graph/text dual-path fusion
- lightweight heuristic rerank
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .lightrag_v2 import LightRAGRetrieverV2


class LightRAGRetrieverV3(LightRAGRetrieverV2):
    """LightRAG retriever v3."""

    name = "lightrag_retriever_v3"

    _RELATION_KEYWORDS = [
        "为什么",
        "原因",
        "影响",
        "关系",
        "联系",
        "区别",
        "对比",
        "推导",
        "依赖",
        "caus",
        "relation",
        "compare",
        "difference",
        "impact",
    ]
    _FACT_KEYWORDS = [
        "是什么",
        "定义",
        "含义",
        "概念",
        "谁",
        "哪里",
        "when",
        "what",
        "define",
        "meaning",
    ]

    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,6}", text.lower())
        stop = {"the", "a", "an", "to", "of", "and", "is", "are", "是", "的", "了", "在"}
        return [t for t in tokens if t and t not in stop]

    def _rewrite_query(self, query: str) -> List[str]:
        """Generate a small set of rule-based query rewrites."""
        base = re.sub(r"\s+", " ", (query or "").strip())
        if not base:
            return []

        rewrites = [base]
        if not re.search(r"[?？]$", base):
            rewrites.append(base + "？")

        if any(k in base for k in ["是什么", "定义", "含义"]) or re.search(
            r"\b(what|define|meaning)\b", base, re.IGNORECASE
        ):
            rewrites.append(f"{base} 的定义")
            rewrites.append(f"解释 {base}")

        if any(k in base for k in ["区别", "对比"]) or re.search(
            r"\b(compare|difference)\b", base, re.IGNORECASE
        ):
            rewrites.append(f"{base} 有什么不同")

        # De-duplicate while preserving order
        seen = set()
        unique: List[str] = []
        for q in rewrites:
            qn = q.strip()
            if not qn or qn in seen:
                continue
            seen.add(qn)
            unique.append(qn)
        return unique[:3]

    def _route_modes(self, query: str, mode: str) -> List[str]:
        """Route query into retrieval modes."""
        if mode and mode != "auto":
            return [mode]

        query_l = (query or "").lower()
        if any(k in query_l for k in self._RELATION_KEYWORDS):
            return ["hybrid", "global", "naive"]
        if any(k in query_l for k in self._FACT_KEYWORDS):
            return ["naive", "local", "hybrid"]
        return ["hybrid", "naive"]

    def _score_candidate(self, query: str, content: str, mode: str) -> float:
        """Heuristic rerank score."""
        if not content:
            return 0.0

        q_tokens = self._tokenize(query)
        c_tokens = set(self._tokenize(content))
        if not q_tokens:
            lexical = 0.0
        else:
            lexical = sum(1 for t in q_tokens if t in c_tokens) / len(q_tokens)

        mode_bonus = {
            "hybrid": 0.12,
            "global": 0.08,
            "local": 0.06,
            "naive": 0.05,
        }.get(mode, 0.0)

        length = len(content)
        length_penalty = 0.0
        if length < 80:
            length_penalty = 0.08
        elif length > 6000:
            length_penalty = 0.05

        return lexical + mode_bonus - length_penalty

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip())

    async def process(
        self,
        query: str,
        kb_name: str,
        mode: str = "hybrid",
        only_need_context: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Search using phase-3 multi-path retrieval + rerank.
        """
        rewrites = self._rewrite_query(query)
        modes = self._route_modes(query, mode)
        self.logger.info(
            f"LightRAG-v3 search in {kb_name}: rewrites={len(rewrites)}, modes={modes}"
        )

        candidates: List[Tuple[float, str, str, str]] = []
        seen_content = set()

        for rq in rewrites:
            for routed_mode in modes:
                result = await super().process(
                    query=rq,
                    kb_name=kb_name,
                    mode=routed_mode,
                    only_need_context=only_need_context,
                    **kwargs,
                )
                content = result.get("content") or result.get("answer") or ""
                normalized = self._normalize_text(content)
                if not normalized or normalized in seen_content:
                    continue
                seen_content.add(normalized)

                score = self._score_candidate(query, normalized, routed_mode)
                candidates.append((score, normalized, rq, routed_mode))

        if not candidates:
            fallback = await super().process(
                query=query,
                kb_name=kb_name,
                mode="hybrid" if mode == "auto" else mode,
                only_need_context=only_need_context,
                **kwargs,
            )
            fallback["provider"] = "lightrag_v3"
            return fallback

        candidates.sort(key=lambda x: x[0], reverse=True)
        top_n = int(kwargs.get("rerank_top_n", 3))
        selected = candidates[: max(1, top_n)]

        fused_sections = []
        for _, content, rq, rm in selected:
            fused_sections.append(f"[mode={rm} | rewrite={rq}]\n{content}")
        fused_content = "\n\n".join(fused_sections)

        return {
            "query": query,
            "answer": fused_content,
            "content": fused_content,
            "mode": mode,
            "provider": "lightrag_v3",
            "metadata": {
                "rewrite_count": len(rewrites),
                "mode_candidates": modes,
                "selected_paths": len(selected),
            },
        }
