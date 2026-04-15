# -*- coding: utf-8 -*-
"""
Pipeline Factory
================

Factory for creating and managing RAG pipelines.

Note: Pipeline imports are lazy to avoid importing heavy dependencies (lightrag, llama_index, etc.)
at module load time. This allows the core services to be imported without RAG dependencies.
"""

from typing import Callable, Dict, List, Optional
import warnings

# Pipeline registry - populated lazily
_PIPELINES: Dict[str, Callable] = {}
_PIPELINES_INITIALIZED = False


def _init_pipelines():
    """Lazily initialize pipeline registry.

    Important:
    - Do NOT import optional heavy dependencies (e.g. llama_index) here.
    - Pipelines must be imported inside their factory callables, so users can
      use other providers without installing every optional dependency.
    """
    global _PIPELINES, _PIPELINES_INITIALIZED
    if _PIPELINES_INITIALIZED:
        return

    def _build_raganything(**kwargs):
        from .pipelines.raganything import RAGAnythingPipeline

        return RAGAnythingPipeline(**kwargs)

    def _build_raganything_docling(**kwargs):
        from .pipelines.raganything_docling import RAGAnythingDoclingPipeline

        return RAGAnythingDoclingPipeline(**kwargs)

    def _build_lightrag(kb_base_dir: Optional[str] = None, **kwargs):
        # LightRAGPipeline is a factory function returning a composed RAGPipeline
        from .pipelines.lightrag import LightRAGPipeline

        return LightRAGPipeline(kb_base_dir=kb_base_dir)

    def _build_lightrag_v1(kb_base_dir: Optional[str] = None, **kwargs):
        # LightRAG v1: phase-1 optimizations
        from .pipelines.lightrag_v1 import LightRAGPipeline

        return LightRAGPipeline(kb_base_dir=kb_base_dir)

    def _build_lightrag_v2(kb_base_dir: Optional[str] = None, **kwargs):
        # LightRAG v2: phase-2 graph quality strategies
        from .pipelines.lightrag_v2 import LightRAGPipeline

        return LightRAGPipeline(kb_base_dir=kb_base_dir)

    def _build_lightrag_v3(kb_base_dir: Optional[str] = None, **kwargs):
        # LightRAG v3: phase-3 retrieval strategies
        from .pipelines.lightrag_v3 import LightRAGPipeline

        return LightRAGPipeline(kb_base_dir=kb_base_dir)

    def _build_lightrag_v4(kb_base_dir: Optional[str] = None, **kwargs):
        # LightRAG v4: phase-4 evolution strategies
        from .pipelines.lightrag_v4 import LightRAGPipeline

        return LightRAGPipeline(kb_base_dir=kb_base_dir)

    def _build_llamaindex(**kwargs):
        # LlamaIndexPipeline depends on optional `llama_index` package.
        # Import it only when explicitly requested.
        from .pipelines.llamaindex import LlamaIndexPipeline

        return LlamaIndexPipeline(**kwargs)

    def _build_llamaindex_v1(**kwargs):
        # LlamaIndex v1: strategies 1~3 (semantic chunk + overlap + parent-child chunking)
        from .pipelines.llamaindex_v1 import LlamaIndexPipeline

        return LlamaIndexPipeline(**kwargs)

    def _build_llamaindex_v2(**kwargs):
        # LlamaIndex v2: add strategies 4 and 9 (hierarchical retrieval + citation enhancement)
        from .pipelines.llamaindex_v2 import LlamaIndexPipeline

        return LlamaIndexPipeline(**kwargs)

    def _build_llamaindex_v3(**kwargs):
        # LlamaIndex v3: add strategies 5 and 6 (query rewrite + hybrid retrieval)
        from .pipelines.llamaindex_v3 import LlamaIndexPipeline

        return LlamaIndexPipeline(**kwargs)

    def _build_llamaindex_v4(**kwargs):
        # LlamaIndex v4: add strategies 7 and 8 (rerank + adaptive top-k)
        from .pipelines.llamaindex_v4 import LlamaIndexPipeline

        return LlamaIndexPipeline(**kwargs)

    _PIPELINES.update(
        {
            "raganything": _build_raganything,  # Full multimodal: MinerU parser, deep analysis (slow, thorough)
            "raganything_docling": _build_raganything_docling,  # Docling parser: Office/HTML friendly, easier setup
            "lightrag": _build_lightrag,  # Knowledge graph: PDFParser, fast text-only (medium speed)
            "lightrag_v1": _build_lightrag_v1,  # phase-1 track
            "lightrag_v2": _build_lightrag_v2,  # phase-2 track
            "lightrag_v3": _build_lightrag_v3,  # phase-3 track
            "lightrag_v4": _build_lightrag_v4,  # phase-4 track
            "llamaindex": _build_llamaindex,  # Vector-only: Simple chunking, fast (fastest)
            "llamaindex_v1": _build_llamaindex_v1,  # v1 experiment track (strategies 1~3)
            "llamaindex_v2": _build_llamaindex_v2,  # v2 experiment track (strategies 4+9 on top of v1)
            "llamaindex_v3": _build_llamaindex_v3,  # v3 experiment track (strategies 5+6 on top of v2)
            "llamaindex_v4": _build_llamaindex_v4,  # v4 experiment track (strategies 7+8 on top of v3)
        }
    )
    _PIPELINES_INITIALIZED = True


def get_pipeline(name: str = "raganything", kb_base_dir: Optional[str] = None, **kwargs):
    """
    Get a pre-configured pipeline by name.

    Args:
        name: Pipeline name (raganything, raganything_docling, lightrag, llamaindex)
        kb_base_dir: Base directory for knowledge bases (passed to all pipelines)
        **kwargs: Additional arguments passed to pipeline constructor

    Returns:
        Pipeline instance

    Raises:
        ValueError: If pipeline name is not found
    """
    _init_pipelines()
    if name not in _PIPELINES:
        available = list(_PIPELINES.keys())
        raise ValueError(f"Unknown pipeline: {name}. Available: {available}")

    factory = _PIPELINES[name]

    try:
        # Handle different pipeline types:
        # - lightrag: callable that accepts kb_base_dir and returns a composed RAGPipeline
        # - llamaindex, raganything, raganything_docling: callables that instantiate class-based pipelines
        if name in ("lightrag", "lightrag_v1", "lightrag_v2", "lightrag_v3", "lightrag_v4"):
            return factory(kb_base_dir=kb_base_dir, **kwargs)

        if kb_base_dir:
            kwargs["kb_base_dir"] = kb_base_dir
        return factory(**kwargs)
    except ImportError as e:
        # Common case: user didn't install optional RAG backend deps (e.g. llama_index).
        raise ValueError(
            f"Pipeline '{name}' is not available because an optional dependency is missing: {e}. "
            f"Please install the required dependency for '{name}', or switch provider to 'raganything'/'lightrag'."
        ) from e


def list_pipelines() -> List[Dict[str, str]]:
    """
    List available pipelines.

    Returns:
        List of pipeline info dictionaries
    """
    return [
        {
            "id": "llamaindex",
            "name": "LlamaIndex",
            "description": "Pure vector retrieval, fastest processing speed.",
        },
        {
            "id": "llamaindex_v1",
            "name": "LlamaIndex v1",
            "description": "Strategies 1~3: semantic chunking + overlap + parent-child chunking.",
        },
        {
            "id": "llamaindex_v2",
            "name": "LlamaIndex v2",
            "description": "Strategies 4+9: hierarchical retrieval + citation enhancement (built on v1).",
        },
        {
            "id": "llamaindex_v3",
            "name": "LlamaIndex v3",
            "description": "Strategies 5+6: query rewrite + hybrid retrieval (built on v2).",
        },
        {
            "id": "llamaindex_v4",
            "name": "LlamaIndex v4",
            "description": "Strategies 7+8: rerank + adaptive top-k (built on v3).",
        },
        {
            "id": "lightrag",
            "name": "LightRAG",
            "description": "Lightweight knowledge graph retrieval, fast processing of text documents.",
        },
        {
            "id": "lightrag_v1",
            "name": "LightRAG v1",
            "description": "Phase 1: cold-start optimization + sentence cleaning + low-information filtering + basic entity normalization.",
        },
        {
            "id": "lightrag_v2",
            "name": "LightRAG v2",
            "description": "Phase 2: relation whitelist/schema + graph noise control (built on v1).",
        },
        {
            "id": "lightrag_v3",
            "name": "LightRAG v3",
            "description": "Phase 3: mode auto-routing + query rewrite + dual-path fusion + lightweight rerank (built on v2).",
        },
        {
            "id": "lightrag_v4",
            "name": "LightRAG v4",
            "description": "Phase 4: incremental manifest update + anchor-constrained retrieval + dynamic update hooks (built on v3).",
        },
        {
            "id": "raganything",
            "name": "RAG-Anything (MinerU)",
            "description": "Multimodal document processing with MinerU parser. Best for academic PDFs with complex equations and formulas.",
        },
        {
            "id": "raganything_docling",
            "name": "RAG-Anything (Docling)",
            "description": "Multimodal document processing with Docling parser. Better for Office documents (.docx, .pptx) and HTML. Easier to install.",
        },
    ]


def register_pipeline(name: str, factory: Callable):
    """
    Register a custom pipeline.

    Args:
        name: Pipeline name
        factory: Factory function or class that creates the pipeline
    """
    _init_pipelines()
    _PIPELINES[name] = factory


def has_pipeline(name: str) -> bool:
    """
    Check if a pipeline exists.

    Args:
        name: Pipeline name

    Returns:
        True if pipeline exists
    """
    _init_pipelines()
    return name in _PIPELINES


# Backward compatibility with old plugin API
def get_plugin(name: str) -> Dict[str, Callable]:
    """
    DEPRECATED: Use get_pipeline() instead.

    Get a plugin by name (maps to pipeline API).
    """
    warnings.warn(
        "get_plugin() is deprecated, use get_pipeline() instead",
        DeprecationWarning,
        stacklevel=2,
    )

    pipeline = get_pipeline(name)
    return {
        "initialize": pipeline.initialize,
        "search": pipeline.search,
        "delete": getattr(pipeline, "delete", lambda kb: True),
    }


def list_plugins() -> List[Dict[str, str]]:
    """
    DEPRECATED: Use list_pipelines() instead.
    """
    warnings.warn(
        "list_plugins() is deprecated, use list_pipelines() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return list_pipelines()


def has_plugin(name: str) -> bool:
    """
    DEPRECATED: Use has_pipeline() instead.
    """
    warnings.warn(
        "has_plugin() is deprecated, use has_pipeline() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return has_pipeline(name)
