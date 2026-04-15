# -*- coding: utf-8 -*-
"""
LlamaIndex Pipeline v3 (Phase B)
================================

在 v2（策略 1/2/3/4/9）基础上新增：
- 策略 5：Query Rewrite
- 策略 6：Hybrid 检索（dense + lexical 融合）
"""

import re
from typing import Any, Dict, List, Set, Tuple

from .llamaindex_v2 import LlamaIndexPipeline as LlamaIndexV2Pipeline


class LlamaIndexPipeline(LlamaIndexV2Pipeline):
    """LlamaIndex v3：继承 v2，并叠加 Phase B 策略。"""

    def __init__(self, kb_base_dir=None):
        super().__init__(kb_base_dir=kb_base_dir)
        # 覆盖 logger 名称，便于评估区分 v2/v3
        from src.logging import get_logger

        self.logger = get_logger("LlamaIndexV3Pipeline")
        self.logger.info("LlamaIndex v3 initialized (v2 + query rewrite + hybrid retrieval)")

    def _tokenize_for_lexical(self, text: str) -> Set[str]:
        """
        轻量词项切分（避免新增依赖）：
        - 英文/数字：按词切分
        - 中文：按单字切分
        """
        if not text:
            return set()
        en_tokens = re.findall(r"[a-z0-9_]+", text.lower())
        zh_tokens = re.findall(r"[\u4e00-\u9fff]", text)
        return set(en_tokens + zh_tokens)

    def _hybrid_rerank_nodes(
        self,
        nodes: List[Any],
        query: str,
        top_k: int,
        alpha: float = 0.75,
    ) -> List[Any]:
        """
        策略6：Hybrid 融合重排
        final = alpha * dense_norm + (1-alpha) * lexical_score
        """
        if not nodes:
            return []

        alpha = max(0.0, min(1.0, float(alpha)))
        query_tokens = self._tokenize_for_lexical(query)

        dense_scores = [float(node_with_score.score or 0.0) for node_with_score in nodes]
        dense_min = min(dense_scores)
        dense_max = max(dense_scores)
        dense_range = dense_max - dense_min

        ranked_items: List[Tuple[float, Any]] = []
        for node_with_score, dense_score in zip(nodes, dense_scores):
            node_text = getattr(node_with_score.node, "text", "") or node_with_score.node.get_content()
            node_tokens = self._tokenize_for_lexical(node_text)
            lexical_score = (
                len(query_tokens.intersection(node_tokens)) / len(query_tokens)
                if query_tokens
                else 0.0
            )

            if dense_range > 1e-9:
                dense_norm = (dense_score - dense_min) / dense_range
            else:
                dense_norm = 1.0

            final_score = alpha * dense_norm + (1.0 - alpha) * lexical_score
            ranked_items.append((final_score, node_with_score))

        ranked_items.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in ranked_items[: max(1, top_k)]]

    def _extract_rewritten_query(self, raw_text: str) -> str:
        """清洗改写结果，只保留单行问题。"""
        if not raw_text:
            return ""
        text = raw_text.strip().strip("`").strip('"').strip("'")
        text = re.sub(
            r"^\s*(重写问题|改写问题|query rewrite|rewritten query)\s*[:：]\s*",
            "",
            text,
            flags=re.I,
        )
        return text.splitlines()[0].strip() if text else ""

    async def _rewrite_query(self, query: str, **kwargs) -> str:
        """
        策略5：Query Rewrite（单改写）
        - 失败自动回退原问题
        - 默认只生成一条改写，控制延迟与成本
        """
        if not query.strip():
            return query

        rewrite_max_chars = int(kwargs.get("rewrite_max_chars", 128))
        prompt = (
            "请将下面用户问题改写为更适合知识库检索的一句话，保持原意，不扩展范围。"
            "只输出改写后的问题，不要解释。\n\n"
            f"原问题：{query}"
        )
        try:
            from src.services.llm import complete as llm_complete

            rewritten = await llm_complete(
                prompt=prompt,
                system_prompt="你是检索查询改写器，只输出精炼、可检索的单句问题。",
                temperature=0.1,
                max_tokens=80,
            )
            cleaned = self._extract_rewritten_query(rewritten)
            if not cleaned:
                return query
            return cleaned[:rewrite_max_chars].rstrip()
        except Exception as e:
            self.logger.warning(f"Query rewrite failed, fallback to original query: {e}")
            return query

    async def search(
        self,
        query: str,
        kb_name: str,
        mode: str = "hybrid",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        v3 搜索（在 v2 上叠加策略 5、6）：
        1) 可选 query rewrite
        2) 召回候选（层级/平铺）
        3) 可选 hybrid 重排
        4) citation 输出
        """
        self.logger.info(f"Searching KB '{kb_name}' with query: {query[:50]}...")
        from pathlib import Path
        import asyncio
        from llama_index.core import StorageContext, load_index_from_storage

        kb_dir = Path(self.kb_base_dir) / kb_name
        storage_dir = kb_dir / "llamaindex_storage"
        if not storage_dir.exists():
            self.logger.warning(f"No LlamaIndex storage found at {storage_dir}")
            return {
                "query": query,
                "answer": "No documents indexed. Please upload documents first.",
                "content": "",
                "mode": mode,
                "provider": "llamaindex_v3",
            }

        try:
            enable_query_rewrite = kwargs.get("enable_query_rewrite", True)
            rewritten_query = query
            if enable_query_rewrite:
                rewritten_query = await self._rewrite_query(query, **kwargs)
                if rewritten_query != query:
                    self.logger.info(f"Query rewritten: '{query[:40]}' -> '{rewritten_query[:40]}'")

            loop = asyncio.get_event_loop()

            def load_and_retrieve():
                storage_context = StorageContext.from_defaults(persist_dir=str(storage_dir))
                index = load_index_from_storage(storage_context)
                top_k = kwargs.get("top_k", 5)
                recall_top_k = kwargs.get("hybrid_recall_top_k", max(top_k * 4, top_k))
                parent_top_k = kwargs.get("parent_top_k", min(3, max(1, top_k)))
                candidate_multiplier = kwargs.get("hierarchical_candidate_multiplier", 4)
                enable_hierarchical_retrieval = kwargs.get("enable_hierarchical_retrieval", True)
                enable_hybrid_retrieval = kwargs.get("enable_hybrid_retrieval", True)
                hybrid_alpha = kwargs.get("hybrid_alpha", 0.75)

                if enable_hierarchical_retrieval:
                    candidate_nodes = self._hierarchical_retrieve(
                        index=index,
                        query=rewritten_query,
                        top_k=recall_top_k,
                        parent_top_k=parent_top_k,
                        candidate_multiplier=candidate_multiplier,
                    )
                else:
                    retriever = index.as_retriever(similarity_top_k=recall_top_k)
                    candidate_nodes = retriever.retrieve(rewritten_query)

                if enable_hybrid_retrieval:
                    nodes = self._hybrid_rerank_nodes(
                        nodes=candidate_nodes,
                        query=rewritten_query,
                        top_k=top_k,
                        alpha=hybrid_alpha,
                    )
                else:
                    nodes = candidate_nodes[:top_k]

                citations = self._build_citations(
                    nodes,
                    top_n=kwargs.get("citation_top_n", top_k),
                    max_chars=kwargs.get("citation_max_chars", 160),
                )
                return (
                    nodes,
                    citations,
                    enable_hierarchical_retrieval,
                    enable_hybrid_retrieval,
                )

            nodes, citations, hierarchical_enabled, hybrid_enabled = await loop.run_in_executor(
                None, load_and_retrieve
            )

            content = "\n\n".join([node.node.text for node in nodes]) if nodes else ""
            return {
                "query": query,
                "answer": content,
                "content": content,
                "rewritten_query": rewritten_query,
                "query_rewrite_applied": rewritten_query != query,
                "citations": citations,
                "retrieval_strategy": (
                    "hierarchical_hybrid"
                    if hierarchical_enabled and hybrid_enabled
                    else "hierarchical_dense"
                    if hierarchical_enabled
                    else "flat_hybrid"
                    if hybrid_enabled
                    else "flat_vector"
                ),
                "mode": mode,
                "provider": "llamaindex_v3",
            }

        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            import traceback

            self.logger.error(traceback.format_exc())
            return {
                "query": query,
                "answer": f"Search failed: {str(e)}",
                "content": "",
                "mode": mode,
                "provider": "llamaindex_v3",
            }

