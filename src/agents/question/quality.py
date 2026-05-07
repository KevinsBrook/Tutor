#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Question quality and schema normalization helpers.
"""

from __future__ import annotations

from typing import Any


SUPPORTED_QUESTION_TYPES = {
    "choice",
    "written",
    "true_false",
    "multiple_choice",
    "fill_blank",
}

BLOOM_LEVELS = {
    "remember",
    "understand",
    "apply",
    "analyze",
    "evaluate",
    "create",
}


def normalize_bloom_level(level: str | None) -> str:
    raw = (level or "").strip().lower()
    aliases = {
        "memory": "remember",
        "comprehend": "understand",
        "analysis": "analyze",
        "evaluation": "evaluate",
        "creation": "create",
    }
    if raw in aliases:
        raw = aliases[raw]
    return raw if raw in BLOOM_LEVELS else "understand"


def normalize_question_type(raw_type: str | None, fallback: str = "written") -> str:
    value = (raw_type or "").strip().lower()
    aliases = {
        "single_choice": "choice",
        "single": "choice",
        "mcq": "choice",
        "subjective": "written",
        "essay": "written",
        "tf": "true_false",
        "judge": "true_false",
        "multi_choice": "multiple_choice",
        "multichoice": "multiple_choice",
        "blank": "fill_blank",
        "fill_in_blank": "fill_blank",
    }
    if value in aliases:
        value = aliases[value]
    if value not in SUPPORTED_QUESTION_TYPES:
        return fallback if fallback in SUPPORTED_QUESTION_TYPES else "written"
    return value


def normalize_question_schema(
    question: dict[str, Any],
    requested_type: str,
    cognitive_level: str,
) -> dict[str, Any]:
    q = dict(question)
    # The caller's requested type is the contract with the UI/evaluator.
    # LLMs often drift from "multiple_choice" back to "choice"; preserving
    # that drift makes a requested multi-select batch become single-select.
    qtype = normalize_question_type(requested_type)
    q["question_type"] = qtype
    q["question"] = str(q.get("question", "")).strip()
    q["correct_answer"] = q.get("correct_answer", "")
    q["explanation"] = str(q.get("explanation", "")).strip()
    q["cognitive_level"] = normalize_bloom_level(cognitive_level)

    if qtype in {"choice", "multiple_choice", "true_false"}:
        options = q.get("options")
        if not isinstance(options, dict):
            options = {}
        if qtype == "true_false":
            options = {"A": "正确", "B": "错误"}
            correct = str(q.get("correct_answer", "")).strip().upper()
            if correct in {"A", "正确", "TRUE", "T"}:
                q["correct_answer"] = "A"
            elif correct in {"B", "错误", "FALSE", "F"}:
                q["correct_answer"] = "B"
            else:
                q["correct_answer"] = "A"
        elif len(options) < 4:
            base = ["选项A", "选项B", "选项C", "选项D"]
            merged: dict[str, str] = {}
            for idx, key in enumerate(["A", "B", "C", "D"]):
                merged[key] = str(options.get(key, base[idx]))
            options = merged
        q["options"] = options

    if qtype == "fill_blank":
        blanks = q.get("blanks")
        if not isinstance(blanks, list):
            blanks = []
        if not blanks and isinstance(q.get("correct_answer"), str):
            blanks = [q["correct_answer"]]
        q["blanks"] = [str(x).strip() for x in blanks if str(x).strip()]

    return q


def _stringify_audit_field(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "; ".join(_stringify_audit_field(item) for item in value if item is not None)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            item_text = _stringify_audit_field(item)
            if item_text:
                parts.append(f"{key}: {item_text}")
        return "; ".join(parts)
    return str(value)


def build_question_audit(
    question: dict[str, Any],
    requested_difficulty: str,
    relevance: str,
    kb_coverage: Any,
    source_refs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    kb_coverage_text = _stringify_audit_field(kb_coverage)
    qtype = question.get("question_type", "written")
    options = question.get("options") if isinstance(question.get("options"), dict) else {}
    option_values = [str(v).strip() for v in options.values()]
    unique_option_count = len({v for v in option_values if v})

    answer = question.get("correct_answer")
    answer_uniqueness = "unknown"
    if qtype in {"choice", "true_false"}:
        answer_uniqueness = "likely_unique" if isinstance(answer, str) and answer else "unclear"
    elif qtype == "multiple_choice":
        answer_uniqueness = "multi_answer_expected"

    distractor_quality = "n/a"
    if qtype in {"choice", "multiple_choice", "true_false"}:
        distractor_quality = "acceptable" if unique_option_count >= max(2, len(option_values) - 1) else "weak"

    length = len(str(question.get("question", "")).strip())
    clarity = "good" if length >= 12 else "weak"
    raw_question = str(question.get("question", ""))

    out_of_scope_risk = "low"
    if relevance == "partial":
        out_of_scope_risk = "medium"
    if not kb_coverage_text or "无" in kb_coverage_text.lower():
        out_of_scope_risk = "high"

    ambiguous_patterns = ["可能", "大概", "也许", "不确定", "无法判断", "待确认"]
    ambiguity = "yes" if any(x in raw_question for x in ambiguous_patterns) else "no"
    latex_format_issue = "yes" if raw_question.count("$") % 2 == 1 else "no"

    refs = source_refs or []
    distractor_meta = question.get("distractor_meta") if isinstance(question.get("distractor_meta"), dict) else {}

    return {
        "requested_difficulty": requested_difficulty,
        "difficulty_alignment": "estimated_match",
        "relevance": relevance,
        "kb_coverage": kb_coverage_text,
        "answer_uniqueness": answer_uniqueness,
        "distractor_quality": distractor_quality,
        "clarity": clarity,
        "out_of_scope_risk": out_of_scope_risk,
        "ambiguous_stem": ambiguity,
        "latex_format_issue": latex_format_issue,
        "source_count": len(refs),
        "distractor_candidate_count": int(distractor_meta.get("candidate_count", 0) or 0),
        "distractor_selected_count": int(distractor_meta.get("selected_count", 0) or 0),
        "distractor_duplicate_removed": int(distractor_meta.get("duplicate_removed", 0) or 0),
        "format_ok": bool(question.get("question")) and bool(question.get("correct_answer")),
    }
