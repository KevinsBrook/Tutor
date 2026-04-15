# -*- coding: utf-8 -*-
"""
LightRAG Pipeline v4 (Phase 4)
==============================

LightRAG v4 = v3 + incremental evolution strategies.
"""

from typing import Optional

from ..components.indexers.lightrag_v4 import LightRAGIndexerV4
from ..components.parsers import PDFParser
from ..components.retrievers.lightrag_v4 import LightRAGRetrieverV4
from ..pipeline import RAGPipeline


def LightRAGPipeline(kb_base_dir: Optional[str] = None) -> RAGPipeline:
    """Create LightRAG v4 pipeline."""
    return (
        RAGPipeline("lightrag_v4", kb_base_dir=kb_base_dir)
        .parser(PDFParser())
        .indexer(LightRAGIndexerV4(kb_base_dir=kb_base_dir))
        .retriever(LightRAGRetrieverV4(kb_base_dir=kb_base_dir))
    )
