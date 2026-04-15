# -*- coding: utf-8 -*-
"""
LightRAG Runtime v1
===================

Shared runtime cache for LightRAG phase-1 components.
"""

import asyncio
from pathlib import Path
import sys
from typing import Any, Dict

from src.logging import get_logger
from src.services.embedding import get_embedding_client
from src.services.llm import get_llm_client


class LightRAGRuntimeV1:
    """
    Shared runtime for lightrag_v1 indexer/retriever.

    Phase-1 target:
    - Reduce cold-start overhead by caching instances.
    - Initialize storages/status once per working directory.
    """

    _instances: Dict[str, Any] = {}
    _initialized_dirs: set[str] = set()
    _init_locks: Dict[str, asyncio.Lock] = {}
    _logger = get_logger("LightRAGRuntimeV1")

    @classmethod
    def get_or_create(cls, working_dir: str):
        """Get or create a LightRAG instance for a working directory."""
        if working_dir in cls._instances:
            return cls._instances[working_dir]

        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        raganything_path = project_root.parent / "raganything" / "RAG-Anything"
        if raganything_path.exists() and str(raganything_path) not in sys.path:
            sys.path.insert(0, str(raganything_path))

        from lightrag import LightRAG

        llm_client = get_llm_client()
        embed_client = get_embedding_client()

        rag = LightRAG(
            working_dir=working_dir,
            llm_model_func=llm_client.get_model_func(),
            embedding_func=embed_client.get_embedding_func(),
        )
        cls._instances[working_dir] = rag
        return rag

    @classmethod
    async def ensure_initialized(cls, working_dir: str, rag: Any):
        """Initialize storages/status once per working_dir."""
        if working_dir in cls._initialized_dirs:
            return

        lock = cls._init_locks.setdefault(working_dir, asyncio.Lock())
        async with lock:
            if working_dir in cls._initialized_dirs:
                return

            await rag.initialize_storages()
            from lightrag.kg.shared_storage import initialize_pipeline_status

            await initialize_pipeline_status()

            cls._initialized_dirs.add(working_dir)
            cls._logger.info(f"LightRAG runtime initialized: {working_dir}")
