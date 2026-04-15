# -*- coding: utf-8 -*-
"""
LightRAG Indexer v2 (Phase 2)
=============================

Built on v1 and adds phase-2 graph quality strategies:
- relation whitelist mapping
- relation schema normalization
- graph noise control (entity/relation filtering)
"""

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from ...types import Document
from .lightrag_v1 import LightRAGIndexerV1, _TextPreprocessorV1
from ..lightrag_runtime_v1 import LightRAGRuntimeV1


class _RelationSchemaV2:
    """
    Rule-based relation schema:
    Raw expressions -> canonical relation types.
    """

    RELATION_PATTERNS: List[Tuple[str, List[re.Pattern[str]]]] = [
        (
            "DEFINES",
            [
                re.compile(r"\b(is|are defined as|refers to|means)\b", re.IGNORECASE),
                re.compile(r"(定义为|是指|指的是)"),
            ],
        ),
        (
            "CONTAINS",
            [
                re.compile(r"\b(include|includes|consists of|contains)\b", re.IGNORECASE),
                re.compile(r"(包括|包含|由.+组成|由.+构成)"),
            ],
        ),
        (
            "CAUSES",
            [
                re.compile(r"\b(cause|causes|lead to|results in|because of)\b", re.IGNORECASE),
                re.compile(r"(导致|造成|引起|由于|因此)"),
            ],
        ),
        (
            "PREREQUISITE",
            [
                re.compile(r"\b(prerequisite|require|requires|depends on)\b", re.IGNORECASE),
                re.compile(r"(前提是|依赖于|需要先)"),
            ],
        ),
        (
            "DERIVES",
            [
                re.compile(r"\b(derive|derived from|deduce|infer)\b", re.IGNORECASE),
                re.compile(r"(推出|推导出|可得|由此得到)"),
            ],
        ),
        (
            "COMPARES",
            [
                re.compile(r"\b(compare|compared to|different from|versus)\b", re.IGNORECASE),
                re.compile(r"(相比|区别在于|不同于|对比)"),
            ],
        ),
    ]

    # Very light entity extraction to avoid noisy graph hints.
    ENTITY_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,31}|[\u4e00-\u9fff]{2,16}")

    @classmethod
    def classify_relation(cls, sentence: str) -> str:
        for relation_type, patterns in cls.RELATION_PATTERNS:
            if any(pattern.search(sentence) for pattern in patterns):
                return relation_type
        return "OTHER"

    @classmethod
    def extract_entities(cls, sentence: str) -> List[str]:
        entities: List[str] = []
        for match in cls.ENTITY_PATTERN.findall(sentence):
            token = match.strip()
            if not token:
                continue
            # Noise control: remove too-short/too-generic tokens.
            if len(token) <= 1:
                continue
            if token.lower() in {"the", "this", "that", "and", "for", "with", "from"}:
                continue
            entities.append(token)
        # Deduplicate while keeping order.
        seen = set()
        unique_entities: List[str] = []
        for token in entities:
            if token in seen:
                continue
            seen.add(token)
            unique_entities.append(token)
        return unique_entities

    @classmethod
    def build_relation_hints(cls, text: str, max_hints: int = 80) -> List[str]:
        """
        Build normalized relation hints:
        [RELATION] <HEAD> --TYPE--> <TAIL>
        """
        if not text:
            return []

        # Sentence split for hint extraction.
        sentences = re.split(r"[\n。！？!?;；]+", text)
        hints: List[str] = []
        for raw_sentence in sentences:
            sentence = raw_sentence.strip()
            if len(sentence) < 12:
                continue

            relation_type = cls.classify_relation(sentence)
            entities = cls.extract_entities(sentence)
            if len(entities) < 2:
                continue

            head, tail = entities[0], entities[1]
            # Phase-2 noise control: skip OTHER with weak entities.
            if relation_type == "OTHER":
                if len(head) < 2 or len(tail) < 2:
                    continue

            hints.append(f"[RELATION] {head} --{relation_type}--> {tail}")
            if len(hints) >= max_hints:
                break

        return hints


class LightRAGIndexerV2(LightRAGIndexerV1):
    """
    LightRAG indexer v2 (phase 2).
    """

    name = "lightrag_indexer_v2"

    def _load_alias_map(self, kb_name: str, **kwargs) -> Dict[str, str]:
        # v2 prefers dedicated alias file, then falls back to v1 behavior.
        alias_file = Path(self.kb_base_dir) / kb_name / "entity_aliases_v2.json"
        if alias_file.exists():
            try:
                import json

                with open(alias_file, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {
                        str(k).strip(): str(v).strip()
                        for k, v in data.items()
                        if str(k).strip() and str(v).strip()
                    }
            except Exception as e:
                self.logger.warning(f"Failed to load alias map from {alias_file}: {e}")

        return super()._load_alias_map(kb_name, **kwargs)

    async def process(self, kb_name: str, documents: List[Document], **kwargs) -> bool:
        """
        Build LightRAG index with phase-2 graph quality enhancements.
        """
        self.logger.info(f"Building knowledge graph for {kb_name} (v2)...")
        working_dir = self._working_dir(kb_name)

        from src.logging.adapters import LightRAGLogContext

        with LightRAGLogContext(scene="LightRAG-Indexer-v2"):
            rag = LightRAGRuntimeV1.get_or_create(working_dir)
            await LightRAGRuntimeV1.ensure_initialized(working_dir, rag)

            alias_map = self._load_alias_map(kb_name, **kwargs)
            for doc in documents:
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

                await rag.ainsert(enriched_content)

        self.logger.info("Knowledge graph built successfully (v2)")
        return True
