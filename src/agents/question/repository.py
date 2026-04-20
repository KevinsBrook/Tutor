#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Question generation repository abstraction.

Phase 6 (storage evolution) baseline:
- Isolate persistence contract from coordinator workflow
- Keep JSON compatibility
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Protocol


class QuestionRunRepository(Protocol):
    def save_knowledge(self, batch_dir: Path, retrieval_result: dict[str, Any]) -> None: ...

    def save_plan(self, batch_dir: Path, plan: dict[str, Any]) -> None: ...

    def save_question_result(self, batch_dir: Path, result: dict[str, Any]) -> None: ...

    def save_summary(self, batch_dir: Path, summary: dict[str, Any]) -> None: ...


@dataclass
class JsonQuestionRunRepository:
    """JSON file-based repository implementation."""

    def save_knowledge(self, batch_dir: Path, retrieval_result: dict[str, Any]) -> None:
        knowledge_file = batch_dir / "knowledge.json"
        payload = {
            "queries": retrieval_result.get("queries", []),
            "retrievals": retrieval_result.get("retrievals", []),
        }
        with open(knowledge_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def save_plan(self, batch_dir: Path, plan: dict[str, Any]) -> None:
        plan_file = batch_dir / "plan.json"
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)

    def save_question_result(self, batch_dir: Path, result: dict[str, Any]) -> None:
        question_id = result.get("question_id", "q_unknown")
        question_dir = batch_dir / question_id
        question_dir.mkdir(parents=True, exist_ok=True)

        with open(question_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    def save_summary(self, batch_dir: Path, summary: dict[str, Any]) -> None:
        summary_file = batch_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

