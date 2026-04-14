# -*- coding: utf-8 -*-
"""
LightRAG Indexer v1 (Phase 1)
=============================

Phase-1 optimizations:
- cold-start optimization via runtime cache
- rule-based sentence cleaning
- low-information block filtering
- basic entity normalization (alias map)
"""

from pathlib import Path
import re
from typing import Dict, List, Optional
import unicodedata

from ...types import Document
from ..base import BaseComponent
from ..lightrag_runtime_v1 import LightRAGRuntimeV1


class _TextPreprocessorV1:
    """Rule-based preprocessing pipeline for phase 1."""

    _NOISE_LINE_PATTERNS = [
        re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
        re.compile(r"^\s*第\s*\d+\s*页\s*$"),
        re.compile(r"^\s*(目录|contents?)\s*$", re.IGNORECASE),
        re.compile(r"^\s*(版权所有|copyright).*$", re.IGNORECASE),
        re.compile(r"^\s*all rights reserved\.?\s*$", re.IGNORECASE),
    ]
    _LOW_INFO_KEYWORDS = [
        "版权所有",
        "copyright",
        "all rights reserved",
        "目录",
        "contents",
    ]

    @classmethod
    def preprocess(cls, text: str, alias_map: Dict[str, str]) -> str:
        normalized = cls._normalize_text(text)
        denoised = cls._remove_noise_lines(normalized)
        blocks = cls._split_blocks(denoised)

        kept_blocks: List[str] = []
        for block in blocks:
            normalized_block = cls._normalize_block_whitespace(block)
            if not normalized_block:
                continue
            if cls._is_low_information(normalized_block):
                continue
            entity_normalized = cls._normalize_entities(normalized_block, alias_map)
            sentence_cleaned = cls._sentence_cleanup(entity_normalized)
            if sentence_cleaned:
                kept_blocks.append(sentence_cleaned)

        return "\n\n".join(kept_blocks).strip()

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = unicodedata.normalize("NFKC", text or "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def _remove_noise_lines(cls, text: str) -> str:
        kept_lines: List[str] = []
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                kept_lines.append("")
                continue

            is_noise = any(pattern.match(line) for pattern in cls._NOISE_LINE_PATTERNS)
            if not is_noise:
                kept_lines.append(line)

        cleaned = "\n".join(kept_lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _split_blocks(text: str) -> List[str]:
        if not text:
            return []
        blocks = re.split(r"\n\s*\n", text)
        return [block.strip() for block in blocks if block and block.strip()]

    @staticmethod
    def _normalize_block_whitespace(block: str) -> str:
        return re.sub(r"\s+", " ", block or "").strip()

    @classmethod
    def _is_low_information(cls, block: str) -> bool:
        content = (block or "").strip()
        if not content:
            return True
        if len(content) < 40:
            return True

        lower = content.lower()
        if any(keyword in lower for keyword in cls._LOW_INFO_KEYWORDS) and len(content) < 200:
            return True

        symbol_count = len(re.findall(r"[^\w\s\u4e00-\u9fff]", content))
        digit_count = len(re.findall(r"\d", content))
        total = max(len(content), 1)
        if symbol_count / total > 0.45:
            return True
        if digit_count / total > 0.55:
            return True

        tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", lower)
        if len(tokens) >= 12:
            unique_ratio = len(set(tokens)) / len(tokens)
            if unique_ratio < 0.35:
                return True

        return False

    @staticmethod
    def _normalize_entities(text: str, alias_map: Dict[str, str]) -> str:
        if not alias_map:
            return text

        normalized = text
        for alias, canonical in alias_map.items():
            alias_text = (alias or "").strip()
            canonical_text = (canonical or "").strip()
            if not alias_text or not canonical_text or alias_text == canonical_text:
                continue

            if re.search(r"[A-Za-z0-9_]", alias_text):
                pattern = re.compile(rf"\b{re.escape(alias_text)}\b", re.IGNORECASE)
                normalized = pattern.sub(canonical_text, normalized)
            else:
                normalized = normalized.replace(alias_text, canonical_text)

        return normalized

    @staticmethod
    def _sentence_cleanup(text: str) -> str:
        if not text:
            return text
        text = re.sub(r"(?<=[。！？!?；;])\s+", "\n", text)
        text = re.sub(r"(?<=[.!?])\s+(?=[A-Z])", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class LightRAGIndexerV1(BaseComponent):
    """LightRAG indexer v1."""

    name = "lightrag_indexer_v1"

    def __init__(self, kb_base_dir: Optional[str] = None):
        super().__init__()
        self.kb_base_dir = kb_base_dir or str(
            Path(__file__).resolve().parent.parent.parent.parent.parent.parent
            / "data"
            / "knowledge_bases"
        )

    def _working_dir(self, kb_name: str) -> str:
        return str(Path(self.kb_base_dir) / kb_name / "rag_storage")

    def _load_alias_map(self, kb_name: str, **kwargs) -> Dict[str, str]:
        inline_aliases = kwargs.get("entity_aliases")
        if isinstance(inline_aliases, dict):
            return {
                str(k).strip(): str(v).strip()
                for k, v in inline_aliases.items()
                if str(k).strip() and str(v).strip()
            }

        alias_file = Path(self.kb_base_dir) / kb_name / "entity_aliases_v1.json"
        if not alias_file.exists():
            return {}

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

        return {}

    async def process(self, kb_name: str, documents: List[Document], **kwargs) -> bool:
        """Build LightRAG index with phase-1 preprocessing."""
        self.logger.info(f"Building knowledge graph for {kb_name} (v1)...")

        working_dir = self._working_dir(kb_name)
        from src.logging.adapters import LightRAGLogContext

        with LightRAGLogContext(scene="LightRAG-Indexer-v1"):
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

                await rag.ainsert(cleaned_content)

        self.logger.info("Knowledge graph built successfully (v1)")
        return True
