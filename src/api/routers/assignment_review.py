#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Assignment Review API Router
============================

Teacher assignment publish + student submission + auto-review + wrongbook practice.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import uuid
import re
import time
from typing import Any
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.utils.assignment_review_store import get_assignment_review_store
from src.utils.document_validator import DocumentValidator

router = APIRouter()

ASSIGNMENT_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".md",
    ".rtf",
    ".html",
    ".htm",
}


class RubricItem(BaseModel):
    name: str
    description: str = ""
    score: float = 0


class ConfirmPublishRequest(BaseModel):
    teacher_username: str


class ReviewRubricScore(BaseModel):
    name: str
    score: float
    max_score: float = 0
    comment: str = ""


class ReviewWrongbookItem(BaseModel):
    assignment_title: str = ""
    feedback: str
    error_type: str = ""
    knowledge_point: str = ""
    suggestion: str = ""


class ReviewSubmissionRequest(BaseModel):
    teacher_username: str
    total_score: float
    feedback: str = ""
    rubric_scores: list[ReviewRubricScore] = []
    wrongbook_items: list[ReviewWrongbookItem] = []


class RubricDraftRequest(BaseModel):
    title: str
    description: str = ""
    file_names: list[str] = []
    expected_total_score: float = 100


class RubricDraftResponse(BaseModel):
    task_points: list[str]
    rubric_items: list[RubricItem]


class WrongbookPracticeRequest(BaseModel):
    student_username: str
    strategy: str


class WrongbookPracticeResponse(BaseModel):
    item_id: str
    practice: dict[str, Any]


class CreateWrongbookItemRequest(BaseModel):
    student_username: str
    assignment_id: str = "custom_practice"
    assignment_title: str = "自定义练习"
    feedback: str
    error_type: str = ""
    knowledge_point: str = ""
    suggestion: str = ""
    source_submission_id: str = ""


def _save_uploaded_files(
    files: list[UploadFile],
    folder: Path,
) -> list[dict[str, Any]]:
    folder.mkdir(parents=True, exist_ok=True)
    stored: list[dict[str, Any]] = []

    for file in files:
        if not file.filename:
            continue
        filename = DocumentValidator.validate_upload_safety(
            file.filename,
            None,
            ASSIGNMENT_ALLOWED_EXTENSIONS,
        )
        target = folder / filename
        with open(target, "wb") as out:
            shutil.copyfileobj(file.file, out)
        stored.append(
            {
                "filename": filename,
                "path": str(target),
                "size": target.stat().st_size if target.exists() else 0,
            }
        )
    return stored


def _split_task_points(title: str, description: str, file_names: list[str]) -> list[str]:
    text = "\n".join([title.strip(), description.strip(), "；".join(file_names)]).strip()
    if not text:
        return []
    parts = re.split(r"[。\n；;！？!?]", text)
    points: list[str] = []
    for part in parts:
        p = part.strip(" \t\r\n-•:：")
        if len(p) < 4:
            continue
        if p in points:
            continue
        points.append(p)
        if len(points) >= 6:
            break
    return points


def _build_rubric_items(
    task_points: list[str], raw_text: str, expected_total_score: float
) -> list[RubricItem]:
    total = expected_total_score if expected_total_score > 0 else 100
    text = raw_text.lower()

    names: list[tuple[str, str]] = []
    if any(k in text for k in ["实验", "lab", "数据", "结果"]):
        names.extend(
            [
                ("实验设计与过程", "目标明确，过程完整，关键步骤可复现"),
                ("结果记录与分析", "结果准确，分析有依据，能够解释现象"),
            ]
        )
    if any(k in text for k in ["代码", "编程", "实现", "程序"]):
        names.extend(
            [
                ("实现正确性", "核心功能满足要求，结果正确"),
                ("代码质量与规范", "结构清晰，命名规范，可维护性较好"),
            ]
        )
    if any(k in text for k in ["报告", "文档", "总结", "论文"]):
        names.extend(
            [
                ("内容完整性", "要点覆盖完整，信息组织合理"),
                ("表达与结构", "逻辑清晰，术语准确，表达流畅"),
            ]
        )

    names.extend(
        [
            ("任务完成度", "是否完整覆盖题目要求"),
            ("思考深度与反思", "是否体现分析、反思与改进意识"),
        ]
    )

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, desc in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append((name, desc))
    selected = deduped[:4]
    if not selected:
        selected = [
            ("任务完成度", "是否完整覆盖题目要求"),
            ("准确性", "内容与结果是否准确"),
            ("表达与结构", "逻辑清晰、条理明确"),
            ("思考深度", "是否体现分析与反思"),
        ]

    count = len(selected)
    base_score = round(total / count, 2)
    items: list[RubricItem] = []
    for idx, (name, desc) in enumerate(selected):
        score = base_score
        if idx == count - 1:
            assigned = sum(item.score for item in items)
            score = round(total - assigned, 2)
        items.append(RubricItem(name=name, description=desc, score=score))

    if task_points:
        first = items[0]
        first.description = f"{first.description}；重点关注：{task_points[0]}"
    return items


def _normalize_keywords(text: str) -> set[str]:
    if not text:
        return set()
    zh_words = re.findall(r"[\u4e00-\u9fa5]{2,}", text)
    en_words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    words = set(zh_words + en_words)
    stop_words = {"作业", "报告", "内容", "进行", "以及", "通过", "完成", "学生", "老师"}
    return {w for w in words if w not in stop_words}


def _build_auto_review(
    assignment: dict[str, Any],
    answer_text: str,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    rubric_items = assignment.get("rubric_items", []) or []
    assignment_text = "\n".join(
        [
            assignment.get("title", ""),
            assignment.get("description", ""),
            " ".join(item.get("name", "") for item in rubric_items),
        ]
    )

    assignment_keywords = _normalize_keywords(assignment_text)
    answer_keywords = _normalize_keywords(answer_text)

    overlap = assignment_keywords.intersection(answer_keywords)
    relevance_ratio = 0.0
    if assignment_keywords:
        relevance_ratio = len(overlap) / len(assignment_keywords)

    text_len_score = min(1.0, len(answer_text.strip()) / 300)
    file_bonus = 0.15 if len(files) > 0 else 0.0
    completeness_ratio = min(1.0, text_len_score * 0.85 + file_bonus)

    relevance_score = round(relevance_ratio * 100, 1)
    rubric_scores: list[dict[str, Any]] = []
    weak_dims: list[dict[str, Any]] = []

    if not rubric_items:
        rubric_items = [
            {"name": "任务完成度", "score": 40},
            {"name": "准确性", "score": 30},
            {"name": "表达清晰度", "score": 30},
        ]

    for item in rubric_items:
        max_score = float(item.get("score", 0) or 0)
        if max_score <= 0:
            continue
        name = str(item.get("name", "未命名维度"))
        dim_factor = 0.6 * relevance_ratio + 0.4 * completeness_ratio
        if any(k in name for k in ["准确", "正确", "分析"]):
            dim_factor = 0.7 * relevance_ratio + 0.3 * completeness_ratio
        elif any(k in name for k in ["表达", "结构", "规范"]):
            dim_factor = 0.5 * relevance_ratio + 0.5 * completeness_ratio

        got = round(max_score * max(0.25, min(1.0, dim_factor)), 1)
        comment = "达到预期" if got / max_score >= 0.75 else "建议加强"
        row = {"name": name, "score": got, "max_score": max_score, "comment": comment}
        rubric_scores.append(row)
        if got / max_score < 0.65:
            weak_dims.append(row)

    total_score = round(sum(x["score"] for x in rubric_scores), 1)

    task_points = _split_task_points(
        assignment.get("title", ""),
        assignment.get("description", ""),
        [f.get("filename", "") for f in assignment.get("files", [])],
    )

    missing_points: list[str] = []
    for point in task_points[:3]:
        key_set = _normalize_keywords(point)
        if key_set and key_set.isdisjoint(answer_keywords):
            missing_points.append(point)

    errors: list[dict[str, Any]] = []
    for dim in weak_dims:
        errors.append(
            {
                "type": "维度薄弱",
                "dimension": dim["name"],
                "detail": f"{dim['name']} 得分较低（{dim['score']}/{dim['max_score']}）",
            }
        )

    suggestions: list[str] = []
    if relevance_score < 55:
        suggestions.append("先对照作业目标重写提纲，确保每个要求都有对应内容。")
    if len(answer_text.strip()) < 120:
        suggestions.append("补充关键过程、结果解释与结论，避免只写简短答案。")
    for dim in weak_dims[:2]:
        suggestions.append(f"围绕“{dim['name']}”补做 1-2 道同类练习并复盘。")
    if not suggestions:
        suggestions.append("整体完成较好，可尝试提升表达精炼度与反思深度。")

    summary = (
        f"相关性 {relevance_score} 分，总分 {total_score} 分。"
        f"已识别 {len(errors)} 个待改进点，建议按维度逐项优化。"
    )

    return {
        "generated_at": time.time(),
        "relevance_score": relevance_score,
        "total_score": total_score,
        "rubric_scores": rubric_scores,
        "errors": errors,
        "missing_points": missing_points,
        "suggestions": suggestions,
        "summary": summary,
    }


def _build_practice(strategy: str, wrong_item: dict[str, Any]) -> dict[str, Any]:
    kp = wrong_item.get("knowledge_point") or "相关知识点"
    feedback = wrong_item.get("feedback") or "本题存在薄弱点"
    suggestion = wrong_item.get("suggestion") or "建议复盘后再练"

    strategy_map = {
        "same_point": ("同知识点再练", "中等"),
        "harder": ("提升难度再练", "较难"),
        "easier": ("降低难度巩固", "基础"),
        "variant": ("变式训练", "中等"),
    }
    label, difficulty = strategy_map.get(strategy, strategy_map["same_point"])

    prompt = (
        f"围绕知识点“{kp}”生成一题{label}任务：\n"
        f"- 背景：{feedback}\n"
        f"- 要求：{suggestion}\n"
        f"- 难度：{difficulty}\n"
        "请给出题干、输入输出或作答要求、评分点。"
    )

    checklist = [
        f"是否正确覆盖知识点：{kp}",
        "是否写出完整过程而非只给结论",
        "是否根据反馈修正了关键错误",
    ]

    return {
        "id": str(uuid.uuid4())[:10],
        "strategy": strategy,
        "strategy_label": label,
        "difficulty": difficulty,
        "title": f"{kp} - {label}",
        "prompt": prompt,
        "checklist": checklist,
        "expected_answer_points": [
            "概念定义准确",
            "步骤完整",
            "结果与分析一致",
        ],
        "created_at": time.time(),
    }


@router.post("/teacher/rubric-draft", response_model=RubricDraftResponse)
async def generate_rubric_draft(request: RubricDraftRequest):
    task_points = _split_task_points(
        title=request.title,
        description=request.description,
        file_names=request.file_names,
    )
    if not task_points:
        task_points = [
            "明确作业目标与完成范围",
            "按步骤完成并保留关键过程",
            "总结结果并说明依据",
        ]

    raw_text = "\n".join([request.title, request.description, " ".join(request.file_names)])
    rubric_items = _build_rubric_items(task_points, raw_text, request.expected_total_score)
    return RubricDraftResponse(task_points=task_points, rubric_items=rubric_items)


@router.get("/teacher/assignments")
async def list_teacher_assignments(teacher_username: str):
    store = get_assignment_review_store()
    assignments = store.list_teacher_assignments(teacher_username)
    return {"assignments": assignments, "total": len(assignments)}


@router.post("/teacher/assignments")
async def create_assignment(
    teacher_username: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    rubric_json: str = Form("[]"),
    files: list[UploadFile] = File(default_factory=list),
):
    store = get_assignment_review_store()
    assignment_id = f"asg_{uuid.uuid4().hex[:10]}"

    try:
        parsed = json.loads(rubric_json or "[]")
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise ValueError("rubric_json must be a JSON array")
        rubric_items = [RubricItem(**item) for item in parsed]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid rubric_json: {exc}") from exc

    upload_folder = (
        store.paths.uploads_root / "teacher" / teacher_username / assignment_id / "assignment_files"
    )
    stored_files = _save_uploaded_files(files, upload_folder)

    assignment = store.create_assignment(
        teacher_username=teacher_username,
        title=title,
        description=description,
        rubric_items=[item.model_dump() for item in rubric_items],
        files=stored_files,
        assignment_id=assignment_id,
    )
    return {"success": True, "assignment": assignment}


@router.post("/teacher/assignments/{assignment_id}/confirm")
async def confirm_assignment_publish(assignment_id: str, request: ConfirmPublishRequest):
    store = get_assignment_review_store()
    assignment = store.confirm_assignment(assignment_id, request.teacher_username)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found or not owned by teacher")
    return {"success": True, "assignment": assignment}


@router.get("/student/published")
async def list_published_assignments():
    store = get_assignment_review_store()
    assignments = store.list_published_assignments()
    return {"assignments": assignments, "total": len(assignments)}


@router.get("/student/submissions")
async def list_student_submissions(student_username: str):
    store = get_assignment_review_store()
    submissions = store.list_student_submissions(student_username)
    return {"submissions": submissions, "total": len(submissions)}


@router.get("/teacher/submissions")
async def list_teacher_submissions(teacher_username: str):
    store = get_assignment_review_store()
    submissions = store.list_teacher_submissions(teacher_username)
    return {"submissions": submissions, "total": len(submissions)}


@router.post("/student/submissions")
async def submit_assignment(
    student_username: str = Form(...),
    assignment_id: str = Form(...),
    answer_text: str = Form(""),
    files: list[UploadFile] = File(default_factory=list),
):
    store = get_assignment_review_store()
    assignment = store.get_assignment_by_id(assignment_id)
    if not assignment or not assignment.get("confirmed"):
        raise HTTPException(status_code=404, detail="Assignment not found or not published")

    upload_folder = (
        store.paths.uploads_root / "student" / student_username / assignment_id / "submission_files"
    )
    stored_files = _save_uploaded_files(files, upload_folder)

    auto_review = _build_auto_review(assignment=assignment, answer_text=answer_text, files=stored_files)

    submission = store.create_submission(
        student_username=student_username,
        assignment_id=assignment_id,
        answer_text=answer_text,
        files=stored_files,
        auto_review=auto_review,
    )
    return {"success": True, "submission": submission, "auto_review": auto_review}


@router.post("/teacher/submissions/{submission_id}/review")
async def review_submission(submission_id: str, request: ReviewSubmissionRequest):
    store = get_assignment_review_store()
    submission = store.review_submission(
        submission_id=submission_id,
        teacher_username=request.teacher_username,
        total_score=request.total_score,
        feedback=request.feedback,
        rubric_scores=[item.model_dump() for item in request.rubric_scores],
        wrongbook_items=[item.model_dump() for item in request.wrongbook_items],
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found or not owned by teacher")
    return {"success": True, "submission": submission}


@router.get("/student/wrongbook")
async def list_student_wrongbook(student_username: str):
    store = get_assignment_review_store()
    items = store.list_wrongbook_items(student_username)
    return {"items": items, "total": len(items)}


@router.post("/student/wrongbook/{item_id}/practice", response_model=WrongbookPracticeResponse)
async def generate_wrongbook_practice(item_id: str, request: WrongbookPracticeRequest):
    allowed = {"same_point", "harder", "easier", "variant"}
    if request.strategy not in allowed:
        raise HTTPException(status_code=400, detail="Invalid strategy")

    store = get_assignment_review_store()
    items = store.list_wrongbook_items(request.student_username)
    target = next((x for x in items if x.get("id") == item_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Wrongbook item not found")

    practice = _build_practice(request.strategy, target)
    updated = store.append_wrongbook_practice(
        student_username=request.student_username,
        item_id=item_id,
        practice=practice,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Wrongbook item not found")

    return WrongbookPracticeResponse(item_id=item_id, practice=practice)


@router.post("/student/wrongbook/custom")
async def create_custom_wrongbook_item(request: CreateWrongbookItemRequest):
    store = get_assignment_review_store()
    item = store.add_wrongbook_item(
        student_username=request.student_username,
        assignment_id=request.assignment_id,
        assignment_title=request.assignment_title,
        feedback=request.feedback,
        error_type=request.error_type,
        knowledge_point=request.knowledge_point,
        suggestion=request.suggestion,
        source_submission_id=request.source_submission_id,
    )
    return {"success": True, "item": item}
