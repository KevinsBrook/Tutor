# -*- coding: utf-8 -*-
"""
LlamaIndex Pipeline v4
======================

在 v3（策略 1/2/3/4/5/6/9）基础上新增：
- 策略 7：Rerank（二阶段重排）
- 策略 8：Top-K 自适应
"""

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from llama_index.core import StorageContext, load_index_from_storage

from .llamaindex_v3 import LlamaIndexPipeline as LlamaIndexV3Pipeline


class LlamaIndexPipeline(LlamaIndexV3Pipeline):
    """LlamaIndex v4：继承 v3，并叠加策略 7、8。"""

    def __init__(self, kb_base_dir=None):
        super().__init__(kb_base_dir=kb_base_dir)
        from src.logging import get_logger

        self.logger = get_logger("LlamaIndexV4Pipeline")
        self.logger.info("LlamaIndex v4 initialized (v3 + adaptive top-k + rerank)")

    def _adaptive_topk(
        self,
        query: str,
        base_top_k: int,
        min_top_k: int,
        max_top_k: int,
    ) -> Tuple[int, int]:
        """
        策略8：Top-K 自适应
        返回：(final_top_k, recall_top_k)
        """
        q = (query or "").strip()
        token_count = len(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", q.lower()))
        # 复杂查询信号：长度较长、包含对比/推理关键词、问号较多
        complexity = 0
        if token_count >= 14:
            complexity += 1
        if any(k in q.lower() for k in ["why", "how", "compare", "difference", "tradeoff"]):
            complexity += 1
        if any(k in q for k in ["为什么", "如何", "比较", "区别", "推导", "证明"]):
            complexity += 1
        if q.count("?") + q.count("？") >= 1:
            complexity += 1

        if complexity <= 1:
            final_top_k = max(min_top_k, min(base_top_k, max_top_k))
        elif complexity == 2:
            final_top_k = max(min_top_k, min(base_top_k + 2, max_top_k))
        else:
            final_top_k = max(min_top_k, min(base_top_k + 4, max_top_k))

        # 召回池通常要比最终返回更大
        recall_top_k = max(final_top_k * 4, final_top_k + 8)
        return final_top_k, recall_top_k

    def _rerank_nodes(
        self,
        nodes: List[Any],
        query: str,
        top_k: int,
        alpha: float = 0.65,
    ) -> List[Any]:
        """
        策略7：Rerank（二阶段重排）
        结合 dense 分数与 lexical 分数，再做最终排序。
        """
        if not nodes:
            return []

        alpha = max(0.0, min(1.0, float(alpha)))
        query_tokens: Set[str] = self._tokenize_for_lexical(query)

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

            # 给结构化 child chunk 轻微加分（有助于回答精度）
            metadata = dict(getattr(node_with_score.node, "metadata", {}) or {})
            structural_bonus = 0.03 if metadata.get("chunk_level") == "child" else 0.0

            final_score = alpha * dense_norm + (1.0 - alpha) * lexical_score + structural_bonus
            ranked_items.append((final_score, node_with_score))

        ranked_items.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in ranked_items[: max(1, top_k)]]

    async def search(
        self,
        query: str,
        kb_name: str,
        mode: str = "hybrid",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        v4 搜索（在 v3 上新增策略 7、8）：
        1) Query Rewrite（继承 v3）
        2) 自适应 Top-K
        3) 层级/平铺召回
        4) Hybrid（继承 v3）
        5) Rerank（二阶段重排）
        6) Citation 输出
        """
        self.logger.info(f"Searching KB '{kb_name}' with query: {query[:50]}...")

        kb_dir = Path(self.kb_base_dir) / kb_name
        storage_dir = kb_dir / "llamaindex_storage"
        if not storage_dir.exists():
            self.logger.warning(f"No LlamaIndex storage found at {storage_dir}")
            return {
                "query": query,
                "answer": "No documents indexed. Please upload documents first.",
                "content": "",
                "mode": mode,
                "provider": "llamaindex_v4",
            }

        try:
            # v3 能力：问题改写
            enable_query_rewrite = kwargs.get("enable_query_rewrite", True)
            rewritten_query = query
            if enable_query_rewrite:
                rewritten_query = await self._rewrite_query(query, **kwargs)
                if rewritten_query != query:
                    self.logger.info(f"Query rewritten: '{query[:40]}' -> '{rewritten_query[:40]}'")

            base_top_k = int(kwargs.get("top_k", 5))
            min_top_k = int(kwargs.get("adaptive_min_top_k", 3))
            max_top_k = int(kwargs.get("adaptive_max_top_k", 12))
            enable_adaptive_topk = kwargs.get("enable_adaptive_top_k", True)
            enable_rerank = kwargs.get("enable_rerank", True)
            rerank_alpha = float(kwargs.get("rerank_alpha", 0.65))
            enable_hierarchical_retrieval = kwargs.get("enable_hierarchical_retrieval", True)
            enable_hybrid_retrieval = kwargs.get("enable_hybrid_retrieval", True)
            hybrid_alpha = float(kwargs.get("hybrid_alpha", 0.75))

            if enable_adaptive_topk:
                final_top_k, recall_top_k = self._adaptive_topk(
                    query=rewritten_query,
                    base_top_k=base_top_k,
                    min_top_k=min_top_k,
                    max_top_k=max_top_k,
                )
            else:
                final_top_k = max(1, base_top_k)
                recall_top_k = max(final_top_k * 4, final_top_k + 8)

            parent_top_k = int(kwargs.get("parent_top_k", min(3, max(1, final_top_k))))
            candidate_multiplier = int(kwargs.get("hierarchical_candidate_multiplier", 4))

            loop = asyncio.get_event_loop()

            def load_and_retrieve():
                storage_context = StorageContext.from_defaults(persist_dir=str(storage_dir))
                index = load_index_from_storage(storage_context)

                # 召回阶段
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

                # v3 的 hybrid 阶段
                hybrid_pool_k = int(kwargs.get("hybrid_pool_k", max(final_top_k * 2, final_top_k)))
                if enable_hybrid_retrieval:
                    pre_rerank_nodes = self._hybrid_rerank_nodes(
                        nodes=candidate_nodes,
                        query=rewritten_query,
                        top_k=hybrid_pool_k,
                        alpha=hybrid_alpha,
                    )
                else:
                    pre_rerank_nodes = candidate_nodes[:hybrid_pool_k]

                # v4 的 rerank 阶段
                if enable_rerank:
                    nodes = self._rerank_nodes(
                        nodes=pre_rerank_nodes,
                        query=rewritten_query,
                        top_k=final_top_k,
                        alpha=rerank_alpha,
                    )
                else:
                    nodes = pre_rerank_nodes[:final_top_k]

                citations = self._build_citations(
                    nodes,
                    top_n=kwargs.get("citation_top_n", final_top_k),
                    max_chars=kwargs.get("citation_max_chars", 160),
                )
                return nodes, citations

            nodes, citations = await loop.run_in_executor(None, load_and_retrieve)
            content = "\n\n".join([node.node.text for node in nodes]) if nodes else ""

            return {
                "query": query,
                "answer": content,
                "content": content,
                "rewritten_query": rewritten_query,
                "query_rewrite_applied": rewritten_query != query,
                "citations": citations,
                "retrieval_strategy": "v4_adaptive_hybrid_rerank",
                "adaptive_top_k": {
                    "enabled": enable_adaptive_topk,
                    "base_top_k": base_top_k,
                    "final_top_k": final_top_k,
                    "recall_top_k": recall_top_k,
                },
                "rerank_applied": enable_rerank,
                "mode": mode,
                "provider": "llamaindex_v4",
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
                "provider": "llamaindex_v4",
            }

