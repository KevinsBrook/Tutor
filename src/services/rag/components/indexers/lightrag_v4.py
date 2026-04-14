# -*- coding: utf-8 -*-
"""
LightRAG Indexer v4 (Phase 4)
=============================

Built on v2 and adds phase-4 evolution strategies:
- incremental ingestion via manifest hash tracking
- dynamic update strategy hooks (drift detection + rebuild marker)
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Set

from ...types import Document
from .lightrag_v2 import LightRAGIndexerV2, _RelationSchemaV2
from .lightrag_v1 import _TextPreprocessorV1
from ..lightrag_runtime_v1 import LightRAGRuntimeV1


class LightRAGIndexerV4(LightRAGIndexerV2):
    """LightRAG indexer v4."""

    name = "lightrag_indexer_v4"

    def _manifest_path(self, kb_name: str) -> Path:
        return Path(self.kb_base_dir) / kb_name / "ingest_manifest_v4.json"

    def _load_manifest(self, kb_name: str) -> Dict[str, Dict[str, str]]:
        path = self._manifest_path(kb_name)
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                docs = data.get("documents")
                if isinstance(docs, dict):
                    return docs
        except Exception as e:
            self.logger.warning(f"Failed to load ingest manifest: {e}")
        return {}

    def _save_manifest(self, kb_name: str, docs: Dict[str, Dict[str, str]]):
        path = self._manifest_path(kb_name)
        payload = {
            "version": "4",
            "updated_at": datetime.now().isoformat(),
            "documents": docs,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save ingest manifest: {e}")

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _detect_drift(
        self,
        kb_name: str,
        previous_doc_keys: Set[str],
        current_doc_keys: Set[str],
        threshold: float = 0.3,
    ):
        """
        Detect deleted-source drift and mark rebuild hint if needed.

        Note:
        LightRAG doesn't expose stable per-source delete in this code path.
        We mark rebuild-needed metadata when drift exceeds threshold.
        """
        if not previous_doc_keys:
            return
        missing = previous_doc_keys - current_doc_keys
        ratio = len(missing) / max(len(previous_doc_keys), 1)
        if ratio < threshold:
            return

        hint_file = Path(self.kb_base_dir) / kb_name / "update_strategy_v4.json"
        payload = {
            "needs_rebuild": True,
            "reason": "source_drift_exceeds_threshold",
            "deleted_sources": sorted(missing),
            "deleted_ratio": ratio,
            "threshold": threshold,
            "updated_at": datetime.now().isoformat(),
        }
        try:
            with open(hint_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.logger.warning(
                f"KB {kb_name}: source drift detected ({ratio:.2%}), rebuild hint written."
            )
        except Exception as e:
            self.logger.warning(f"Failed to write update strategy hint: {e}")

    async def process(self, kb_name: str, documents: List[Document], **kwargs) -> bool:
        """
        Build LightRAG index with phase-4 incremental update strategy.
        """
        self.logger.info(f"Building knowledge graph for {kb_name} (v4)...")
        working_dir = self._working_dir(kb_name)

        from src.logging.adapters import LightRAGLogContext

        with LightRAGLogContext(scene="LightRAG-Indexer-v4"):
            rag = LightRAGRuntimeV1.get_or_create(working_dir)
            await LightRAGRuntimeV1.ensure_initialized(working_dir, rag)

            alias_map = self._load_alias_map(kb_name, **kwargs)
            manifest = self._load_manifest(kb_name)
            previous_keys = set(manifest.keys())
            new_manifest = dict(manifest)

            changed_count = 0
            skipped_count = 0
            current_keys: Set[str] = set()

            for doc in documents:
                source_key = str(doc.file_path or f"memory:{id(doc)}")
                current_keys.add(source_key)

                if not doc.content:
                    continue

                cleaned_content = _TextPreprocessorV1.preprocess(doc.content, alias_map)
                if not cleaned_content:
                    self.logger.warning(
                        f"Skipped low-information/empty doc after preprocess: {doc.file_path}"
                    )
                    continue

                relation_hints = _RelationSchemaV2.build_relation_hints(cleaned_content)
                if relation_hints:
                    enriched_content = (
                        cleaned_content + "\n\n" + "### RELATION_HINTS_V2\n" + "\n".join(relation_hints)
                    )
                else:
                    enriched_content = cleaned_content

                content_hash = self._hash_text(enriched_content)
                prev_hash = manifest.get(source_key, {}).get("hash")
                if prev_hash == content_hash:
                    skipped_count += 1
                    continue

                await rag.ainsert(enriched_content)
                changed_count += 1
                new_manifest[source_key] = {
                    "hash": content_hash,
                    "updated_at": datetime.now().isoformat(),
                }

            self._save_manifest(kb_name, new_manifest)
            self._detect_drift(kb_name, previous_keys, current_keys)

        self.logger.info(
            f"Knowledge graph built successfully (v4), changed={changed_count}, skipped={skipped_count}"
        )
        return True
