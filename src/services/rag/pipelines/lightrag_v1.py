# -*- coding: utf-8 -*-
"""
LightRAG Pipeline v1 (Phase 1)
==============================

Pure LightRAG pipeline with phase-1 optimizations.
"""

from typing import Optional

from ..components.indexers.lightrag_v1 import LightRAGIndexerV1
from ..components.parsers import PDFParser
from ..components.retrievers.lightrag_v1 import LightRAGRetrieverV1
from ..pipeline import RAGPipeline


def LightRAGPipeline(kb_base_dir: Optional[str] = None) -> RAGPipeline:
    """
    Create LightRAG v1 pipeline.
    """
    return (
        RAGPipeline("lightrag_v1", kb_base_dir=kb_base_dir)
        .parser(PDFParser())
        .indexer(LightRAGIndexerV1(kb_base_dir=kb_base_dir))
        .retriever(LightRAGRetrieverV1(kb_base_dir=kb_base_dir))
    )
