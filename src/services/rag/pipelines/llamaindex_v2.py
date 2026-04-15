# -*- coding: utf-8 -*-
"""
LlamaIndex Pipeline
===================

True LlamaIndex integration using official llama-index library.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from llama_index.core import (
    Document,
    Settings,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr

from src.logging import get_logger
from src.services.embedding import get_embedding_client, get_embedding_config

# Default knowledge base directory
DEFAULT_KB_BASE_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "knowledge_bases"
)


class CustomEmbedding(BaseEmbedding):
    """
    Custom embedding adapter for OpenAI-compatible APIs.

    Works with any OpenAI-compatible endpoint including:
    - Google Gemini (text-embedding-004)
    - OpenAI (text-embedding-ada-002, text-embedding-3-*)
    - Azure OpenAI
    - Local models with OpenAI-compatible API
    """

    _client: Any = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = get_embedding_client()

    @classmethod
    def class_name(cls) -> str:
        return "custom_embedding"

    async def _aget_query_embedding(self, query: str) -> List[float]:
        """Get embedding for a query."""
        embeddings = await self._client.embed([query])
        return embeddings[0]

    async def _aget_text_embedding(self, text: str) -> List[float]:
        """Get embedding for a text."""
        embeddings = await self._client.embed([text])
        return embeddings[0]

    def _get_query_embedding(self, query: str) -> List[float]:
        """Sync version - called by LlamaIndex sync API."""
        # Use nest_asyncio to allow nested event loops
        import nest_asyncio

        nest_asyncio.apply()
        return asyncio.run(self._aget_query_embedding(query))

    def _get_text_embedding(self, text: str) -> List[float]:
        """Sync version - called by LlamaIndex sync API."""
        # Use nest_asyncio to allow nested event loops
        import nest_asyncio

        nest_asyncio.apply()
        return asyncio.run(self._aget_text_embedding(text))

    async def _aget_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts."""
        return await self._client.embed(texts)


class LlamaIndexPipeline:
    """
    True LlamaIndex pipeline using official llama-index library.

    Uses LlamaIndex's native components:
    - VectorStoreIndex for indexing
    - CustomEmbedding for OpenAI-compatible embeddings
    - SentenceSplitter for chunking
    - StorageContext for persistence
    """

    def __init__(self, kb_base_dir: Optional[str] = None):
        """
        Initialize LlamaIndex pipeline.

        Args:
            kb_base_dir: Base directory for knowledge bases
        """
        self.logger = get_logger("LlamaIndexV2Pipeline")
        self.kb_base_dir = kb_base_dir or DEFAULT_KB_BASE_DIR
        # v1 默认切片参数（策略 1~3）
        self.default_parent_chunk_size = 1200
        self.default_parent_chunk_overlap = 150
        self.default_child_chunk_size = 300
        self.default_child_chunk_overlap = 60
        self.default_semantic_breakpoint_percentile = 95
        self.default_semantic_buffer_size = 1
        self._configure_settings()

    def _configure_settings(self):
        """Configure LlamaIndex global settings."""
        # Get embedding config
        embedding_cfg = get_embedding_config()

        # Configure custom embedding that works with any OpenAI-compatible API
        Settings.embed_model = CustomEmbedding()

        self.logger.info(
            f"LlamaIndex v2 configured: embedding={embedding_cfg.model} "
            f"({embedding_cfg.dim}D, {embedding_cfg.binding})"
        )

    def _load_documents(self, file_paths: List[str], robust_encoding: bool = False) -> List[Document]:
        """读取原始文件并转换为 LlamaIndex Document。"""
        documents: List[Document] = []
        for file_path in file_paths:
            path = Path(file_path)
            self.logger.info(f"Parsing: {path.name}")

            if path.suffix.lower() == ".pdf":
                text = self._extract_pdf_text(path)
            else:
                if robust_encoding:
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            text = f.read()
                    except UnicodeDecodeError:
                        with open(path, "r", encoding="latin-1") as f:
                            text = f.read()
                else:
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()

            if not text.strip():
                self.logger.warning(f"Skipped empty document: {path.name}")
                continue

            documents.append(
                Document(
                    text=text,
                    metadata={
                        "file_name": path.name,
                        "file_path": str(path),
                    },
                )
            )
            self.logger.info(f"Loaded: {path.name} ({len(text)} chars)")
        return documents

    def _build_hierarchical_nodes(
        self, documents: List[Document], **kwargs
    ) -> Tuple[List[Any], List[Any]]:
        """
        v1 层级切片（策略 1~3）：
        1) 语义切分（父块，失败回退句子切分）
        2) overlap 子块切分
        3) parent-child 元数据
        """
        from llama_index.core.node_parser import SentenceSplitter

        semantic_breakpoint = kwargs.get(
            "semantic_breakpoint_percentile", self.default_semantic_breakpoint_percentile
        )
        semantic_buffer_size = kwargs.get(
            "semantic_buffer_size", self.default_semantic_buffer_size
        )
        parent_chunk_size = kwargs.get("parent_chunk_size", self.default_parent_chunk_size)
        parent_chunk_overlap = kwargs.get(
            "parent_chunk_overlap", self.default_parent_chunk_overlap
        )
        child_chunk_size = kwargs.get("child_chunk_size", self.default_child_chunk_size)
        child_chunk_overlap = kwargs.get("child_chunk_overlap", self.default_child_chunk_overlap)

        semantic_enabled = True
        try:
            from llama_index.core.node_parser import SemanticSplitterNodeParser

            parent_parser = SemanticSplitterNodeParser(
                embed_model=Settings.embed_model,
                breakpoint_percentile_threshold=semantic_breakpoint,
                buffer_size=semantic_buffer_size,
            )
            parent_nodes = parent_parser.get_nodes_from_documents(documents)
        except Exception as e:
            semantic_enabled = False
            self.logger.warning(f"Semantic splitter unavailable, fallback to sentence splitter: {e}")
            parent_parser = SentenceSplitter(
                chunk_size=parent_chunk_size,
                chunk_overlap=parent_chunk_overlap,
            )
            parent_nodes = parent_parser.get_nodes_from_documents(documents)

        child_parser = SentenceSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap,
        )

        hierarchical_parent_nodes: List[Any] = []
        child_nodes: List[Any] = []

        for parent_idx, parent_node in enumerate(parent_nodes):
            parent_metadata = dict(getattr(parent_node, "metadata", {}) or {})
            parent_metadata.update(
                {
                    "chunk_level": "parent",
                    "chunk_strategy": "semantic" if semantic_enabled else "sentence",
                    "parent_index": parent_idx,
                    "parent_node_id": getattr(parent_node, "node_id", ""),
                }
            )
            parent_node.metadata = parent_metadata

            parent_text = getattr(parent_node, "text", "") or parent_node.get_content()
            if not parent_text.strip():
                continue

            child_docs = [Document(text=parent_text, metadata=dict(parent_metadata))]
            split_children = child_parser.get_nodes_from_documents(child_docs)
            for child_idx, child_node in enumerate(split_children):
                child_metadata = dict(getattr(child_node, "metadata", {}) or {})
                child_metadata.update(
                    {
                        "chunk_level": "child",
                        "child_index": child_idx,
                        "parent_node_id": getattr(parent_node, "node_id", ""),
                    }
                )
                child_node.metadata = child_metadata

            hierarchical_parent_nodes.append(parent_node)
            child_nodes.extend(split_children)

        return hierarchical_parent_nodes, child_nodes

    async def initialize(self, kb_name: str, file_paths: List[str], **kwargs) -> bool:
        """
        Initialize KB using real LlamaIndex components.

        Args:
            kb_name: Knowledge base name
            file_paths: List of file paths to process
            **kwargs: Additional arguments

        Returns:
            True if successful
        """
        self.logger.info(
            f"Initializing KB '{kb_name}' with {len(file_paths)} files using LlamaIndex"
        )

        kb_dir = Path(self.kb_base_dir) / kb_name
        storage_dir = kb_dir / "llamaindex_storage"
        storage_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1) 读取原始文档
            documents = self._load_documents(file_paths, robust_encoding=False)

            if not documents:
                self.logger.error("No valid documents found")
                return False

            self.logger.info(
                f"Building hierarchical chunks for {len(documents)} documents (v1 strategies 1~3)..."
            )
            loop = asyncio.get_event_loop()

            def build_index():
                parent_nodes, child_nodes = self._build_hierarchical_nodes(documents, **kwargs)
                if not child_nodes:
                    raise ValueError("No child chunks generated for indexing")

                storage_context = StorageContext.from_defaults()
                if parent_nodes:
                    # 父块存 docstore，子块入向量索引
                    storage_context.docstore.add_documents(parent_nodes)

                index = VectorStoreIndex(child_nodes, storage_context=storage_context)
                return index, len(parent_nodes), len(child_nodes)

            index, parent_count, child_count = await loop.run_in_executor(None, build_index)
            self.logger.info(
                f"Chunking completed: parent_chunks={parent_count}, child_chunks={child_count}"
            )

            # Persist index
            index.storage_context.persist(persist_dir=str(storage_dir))
            self.logger.info(f"Index persisted to {storage_dir}")

            self.logger.info(f"KB '{kb_name}' initialized successfully with LlamaIndex")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize KB: {e}")
            import traceback

            self.logger.error(traceback.format_exc())
            return False

    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from PDF using PyMuPDF."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(file_path)
            texts = []
            for page in doc:
                texts.append(page.get_text())
            doc.close()
            return "\n\n".join(texts)
        except ImportError:
            self.logger.warning("PyMuPDF not installed. Cannot extract PDF text.")
            return ""
        except Exception as e:
            self.logger.error(f"Failed to extract PDF text: {e}")
            return ""

    def _hierarchical_retrieve(
        self,
        index: Any,
        query: str,
        top_k: int,
        parent_top_k: int,
        candidate_multiplier: int,
    ) -> List[Any]:
        """
        策略4：层级检索（先父后子）
        - 先召回更多子块候选
        - 按 parent_node_id 聚合父块得分
        - 回筛高分父块下的子块
        """
        # 先扩大候选集合，给“父块聚合”留出空间
        candidate_top_k = max(top_k * max(1, candidate_multiplier), top_k)
        retriever = index.as_retriever(similarity_top_k=candidate_top_k)
        candidate_nodes = retriever.retrieve(query)
        if not candidate_nodes:
            return []

        parent_score_map: Dict[str, float] = {}
        for node_with_score in candidate_nodes:
            metadata = dict(getattr(node_with_score.node, "metadata", {}) or {})
            parent_id = metadata.get("parent_node_id")
            if not parent_id:
                continue
            score = float(node_with_score.score or 0.0)
            parent_score_map[parent_id] = max(parent_score_map.get(parent_id, float("-inf")), score)

        if not parent_score_map:
            return candidate_nodes[:top_k]

        # 选出得分最高的父块
        selected_parent_ids: Set[str] = {
            parent_id
            for parent_id, _ in sorted(
                parent_score_map.items(), key=lambda x: x[1], reverse=True
            )[: max(1, parent_top_k)]
        }

        filtered_nodes = []
        for node_with_score in candidate_nodes:
            metadata = dict(getattr(node_with_score.node, "metadata", {}) or {})
            if metadata.get("parent_node_id") in selected_parent_ids:
                filtered_nodes.append(node_with_score)

        # 若过滤后为空，回退到原始候选，避免空召回
        return filtered_nodes[:top_k] if filtered_nodes else candidate_nodes[:top_k]

    def _build_citations(
        self,
        nodes: List[Any],
        top_n: int = 5,
        max_chars: int = 160,
    ) -> List[Dict[str, Any]]:
        """
        策略9：Citation 增强
        返回结构化来源信息，便于前端展示与评估。
        """
        citations: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()

        for rank, node_with_score in enumerate(nodes, 1):
            node = node_with_score.node
            metadata = dict(getattr(node, "metadata", {}) or {})
            file_path = str(metadata.get("file_path", ""))
            parent_id = str(metadata.get("parent_node_id", ""))
            child_idx = str(metadata.get("child_index", ""))
            dedup_key = f"{file_path}|{parent_id}|{child_idx}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            text = getattr(node, "text", "") or node.get_content()
            snippet = " ".join((text or "").split())[:max_chars]
            citations.append(
                {
                    "rank": rank,
                    "file_name": metadata.get("file_name", ""),
                    "file_path": file_path,
                    "parent_node_id": parent_id,
                    "child_index": metadata.get("child_index"),
                    "score": float(node_with_score.score or 0.0),
                    "snippet": snippet,
                }
            )
            if len(citations) >= max(1, top_n):
                break

        return citations

    async def search(
        self,
        query: str,
        kb_name: str,
        mode: str = "hybrid",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Search using LlamaIndex query engine.

        Args:
            query: Search query
            kb_name: Knowledge base name
            mode: Search mode (ignored, LlamaIndex uses similarity)
            **kwargs: Additional arguments (top_k, etc.)

        Returns:
            Search results dictionary
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
                "provider": "llamaindex_v2",
            }

        try:
            # Load index from storage (run in thread pool)
            loop = asyncio.get_event_loop()

            def load_and_retrieve():
                # 从持久化存储加载索引，执行 v2 检索主流程
                storage_context = StorageContext.from_defaults(persist_dir=str(storage_dir))
                index = load_index_from_storage(storage_context)
                top_k = kwargs.get("top_k", 5)
                parent_top_k = kwargs.get("parent_top_k", min(3, max(1, top_k)))
                candidate_multiplier = kwargs.get("hierarchical_candidate_multiplier", 4)
                enable_hierarchical_retrieval = kwargs.get("enable_hierarchical_retrieval", True)

                # 默认启用层级检索；可通过开关回退为普通向量检索
                if enable_hierarchical_retrieval:
                    nodes = self._hierarchical_retrieve(
                        index=index,
                        query=query,
                        top_k=top_k,
                        parent_top_k=parent_top_k,
                        candidate_multiplier=candidate_multiplier,
                    )
                else:
                    retriever = index.as_retriever(similarity_top_k=top_k)
                    nodes = retriever.retrieve(query)

                # 基于最终命中节点生成结构化引用信息
                citations = self._build_citations(
                    nodes,
                    top_n=kwargs.get("citation_top_n", top_k),
                    max_chars=kwargs.get("citation_max_chars", 160),
                )
                return nodes, citations, enable_hierarchical_retrieval

            # Execute retrieval in thread pool to avoid blocking
            nodes, citations, hierarchical_enabled = await loop.run_in_executor(
                None, load_and_retrieve
            )

            # Extract text from retrieved nodes
            context_parts = []
            for node in nodes:
                context_parts.append(node.node.text)

            content = "\n\n".join(context_parts) if context_parts else ""

            return {
                "query": query,
                "answer": content,  # Return context for ChatAgent to use
                "content": content,
                "citations": citations,
                "retrieval_strategy": (
                    "hierarchical" if hierarchical_enabled else "flat_vector"
                ),
                "mode": mode,
                "provider": "llamaindex_v2",
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
                "provider": "llamaindex_v2",
            }

    async def add_documents(self, kb_name: str, file_paths: List[str], **kwargs) -> bool:
        """
        Incrementally add documents to an existing LlamaIndex KB.

        If the storage directory exists, loads the existing index and inserts
        new documents. Otherwise, creates a new index.

        Args:
            kb_name: Knowledge base name
            file_paths: List of file paths to add
            **kwargs: Additional arguments

        Returns:
            True if successful
        """
        self.logger.info(f"Adding {len(file_paths)} documents to KB '{kb_name}' using LlamaIndex")

        kb_dir = Path(self.kb_base_dir) / kb_name
        storage_dir = kb_dir / "llamaindex_storage"

        try:
            # 增量路径复用同一套切片逻辑，确保和 initialize 行为一致
            documents = self._load_documents(file_paths, robust_encoding=True)

            if not documents:
                self.logger.warning("No valid documents to add")
                return False

            loop = asyncio.get_event_loop()

            if storage_dir.exists():
                # Load existing index and insert new documents
                self.logger.info(f"Loading existing index from {storage_dir}...")

                def load_and_insert():
                    storage_context = StorageContext.from_defaults(persist_dir=str(storage_dir))
                    index = load_index_from_storage(storage_context)
                    parent_nodes, child_nodes = self._build_hierarchical_nodes(
                        documents, **kwargs
                    )

                    if parent_nodes:
                        index.storage_context.docstore.add_documents(parent_nodes)
                    if child_nodes:
                        index.insert_nodes(child_nodes)

                    # Persist updated index
                    index.storage_context.persist(persist_dir=str(storage_dir))
                    return len(parent_nodes), len(child_nodes)

                parent_count, child_count = await loop.run_in_executor(None, load_and_insert)
                self.logger.info(
                    f"Added documents: parent_chunks={parent_count}, child_chunks={child_count}"
                )
            else:
                # Create new index (first time)
                self.logger.info(f"Creating new index with {len(documents)} documents...")
                storage_dir.mkdir(parents=True, exist_ok=True)

                def create_index():
                    parent_nodes, child_nodes = self._build_hierarchical_nodes(
                        documents, **kwargs
                    )
                    if not child_nodes:
                        raise ValueError("No child chunks generated for indexing")

                    storage_context = StorageContext.from_defaults()
                    if parent_nodes:
                        storage_context.docstore.add_documents(parent_nodes)

                    index = VectorStoreIndex(child_nodes, storage_context=storage_context)
                    index.storage_context.persist(persist_dir=str(storage_dir))
                    return len(parent_nodes), len(child_nodes)

                parent_count, child_count = await loop.run_in_executor(None, create_index)
                self.logger.info(
                    f"Created new index with hierarchical chunks: parent_chunks={parent_count}, child_chunks={child_count}"
                )

            self.logger.info(f"Successfully added documents to KB '{kb_name}'")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add documents: {e}")
            import traceback

            self.logger.error(traceback.format_exc())
            return False

    async def delete(self, kb_name: str) -> bool:
        """
        Delete knowledge base.

        Args:
            kb_name: Knowledge base name

        Returns:
            True if successful
        """
        import shutil

        kb_dir = Path(self.kb_base_dir) / kb_name

        if kb_dir.exists():
            shutil.rmtree(kb_dir)
            self.logger.info(f"Deleted KB '{kb_name}'")
            return True

        return False
