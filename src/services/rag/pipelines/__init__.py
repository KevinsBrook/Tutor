# -*- coding: utf-8 -*-
"""
Pre-configured Pipelines
========================

Ready-to-use RAG pipelines for common use cases.
"""

from typing import Any

__all__ = [
    "RAGAnythingPipeline",
    "RAGAnythingDoclingPipeline",
    "LightRAGPipeline",
    "LightRAGV1Pipeline",
    "LightRAGV2Pipeline",
    "LightRAGV3Pipeline",
    "LightRAGV4Pipeline",
]

# NOTE:
# - Do NOT import heavy/optional backends at module import time.
# - Users may want `llamaindex` without `raganything`, or vice versa.
# - Accessing an attribute triggers a targeted import via __getattr__.


def __getattr__(name: str) -> Any:
    if name == "LightRAGPipeline":
        from .lightrag import LightRAGPipeline

        return LightRAGPipeline
    if name == "LightRAGV1Pipeline":
        from .lightrag_v1 import LightRAGPipeline

        return LightRAGPipeline
    if name == "LightRAGV2Pipeline":
        from .lightrag_v2 import LightRAGPipeline

        return LightRAGPipeline
    if name == "LightRAGV3Pipeline":
        from .lightrag_v3 import LightRAGPipeline

        return LightRAGPipeline
    if name == "LightRAGV4Pipeline":
        from .lightrag_v4 import LightRAGPipeline

        return LightRAGPipeline
    if name == "RAGAnythingPipeline":
        from .raganything import RAGAnythingPipeline

        return RAGAnythingPipeline
    if name == "RAGAnythingDoclingPipeline":
        from .raganything_docling import RAGAnythingDoclingPipeline

        return RAGAnythingDoclingPipeline
    if name == "LlamaIndexPipeline":
        # Optional dependency: llama_index
        from .llamaindex import LlamaIndexPipeline

        return LlamaIndexPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
