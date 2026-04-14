# -*- coding: utf-8 -*-
"""
LightRAG Pipeline v3 (Phase 3)
==============================

LightRAG v3 = v2 + phase-3 retrieval strategies.
"""

from typing import Optional

from ..components.indexers.lightrag_v2 import LightRAGIndexerV2
from ..components.parsers import PDFParser
from ..components.retrievers.lightrag_v3 import LightRAGRetrieverV3
from ..pipeline import RAGPipeline


def LightRAGPipeline(kb_base_dir: Optional[str] = None) -> RAGPipeline:
    """Create LightRAG v3 pipeline."""
    return (
        RAGPipeline("lightrag_v3", kb_base_dir=kb_base_dir)
        .parser(PDFParser())
        .indexer(LightRAGIndexerV2(kb_base_dir=kb_base_dir))
        .retriever(LightRAGRetrieverV3(kb_base_dir=kb_base_dir))
    )
