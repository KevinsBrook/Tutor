# -*- coding: utf-8 -*-
"""
LightRAG Pipeline v2 (Phase 2)
==============================

LightRAG v2 = v1 + phase-2 graph quality strategies.
"""

from typing import Optional

from ..components.indexers.lightrag_v2 import LightRAGIndexerV2
from ..components.parsers import PDFParser
from ..components.retrievers.lightrag_v2 import LightRAGRetrieverV2
from ..pipeline import RAGPipeline


def LightRAGPipeline(kb_base_dir: Optional[str] = None) -> RAGPipeline:
    """Create LightRAG v2 pipeline."""
    return (
        RAGPipeline("lightrag_v2", kb_base_dir=kb_base_dir)
        .parser(PDFParser())
        .indexer(LightRAGIndexerV2(kb_base_dir=kb_base_dir))
        .retriever(LightRAGRetrieverV2(kb_base_dir=kb_base_dir))
    )
