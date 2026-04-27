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

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.utils.assignment_review_store import get_assignment_review_store
from src.core.database import get_db
from src.core.models import Course, CourseChapter, KnowledgePoint, Student, Teacher, User
from src.services.mastery import apply_mastery_event
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
    knowledge_point_id: int | None = None
    suggestion: str = ""


class ReviewSubmissionRequest(BaseModel):
    teacher_username: str
    total_score: float
    feedback: str = ""
    rubric_scores: list[ReviewRubricScore] = Field(default_factory=list)
    wrongbook_items: list[ReviewWrongbookItem] = Field(default_factory=list)


class RubricDraftRequest(BaseModel):
    title: str
    description: str = ""
    file_names: list[str] = Field(default_factory=list)
    course_id: int | None = None
    chapter_id: int | None = None
    expected_total_score: float = 100


class RubricDraftResponse(BaseModel):
    task_points: list[str]
    rubric_items: list[RubricItem]


class WrongbookPracticeRequest(BaseModel):
    student_username: str
    strategy: str


class WrongbookPracticeResultRequest(BaseModel):
    student_username: str
    knowledge_point_id: int | None = None
    source_id: str | None = None
    score: float | None = None
    max_score: float | None = None
    is_correct: bool | None = None
    difficulty: str = "medium"
    answer_quality: str | None = None
    used_hint: bool = False
    attempt_count: int | None = Field(default=None, ge=1, le=20)
    note: str = ""


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
    knowledge_point_id: int | None = None
    suggestion: str = ""
    source_submission_id: str = ""


class ConfirmKnowledgeCandidate(BaseModel):
    name: str
    description: str = ""
    priority: int = Field(default=3, ge=1, le=5)
    chapter_id: int | None = None


class ConfirmKnowledgeCandidatesRequest(BaseModel):
    teacher_username: str
    candidates: list[ConfirmKnowledgeCandidate]


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


def _extract_text_from_file(path: str | Path, limit: int = 12000) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(file_path))
            pages = []
            for page in reader.pages[:20]:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text.strip())
            return "\n".join(pages)[:limit]
        if suffix in {".txt", ".md", ".rtf", ".html", ".htm"}:
            return file_path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except Exception:
        return ""
    return ""


def _get_teacher_by_username(db: Session, username: str) -> Teacher | None:
    user = db.query(User).filter(User.username == username, User.role == "teacher").first()
    if not user:
        return None
    return db.query(Teacher).filter(Teacher.user_id == user.id).first()


def _get_student_by_username(db: Session, username: str) -> Student | None:
    user = db.query(User).filter(User.username == username, User.role == "student").first()
    if not user:
        return None
    return db.query(Student).filter(Student.user_id == user.id).first()


def _apply_optional_mastery_update(
    db: Session,
    *,
    student_username: str,
    knowledge_point_id: int | None,
    source_type: str,
    source_id: str,
    score: float | None = None,
    max_score: float | None = None,
    is_correct: bool | None = None,
    difficulty: str = "medium",
    answer_quality: str | None = None,
    used_hint: bool = False,
    attempt_count: int | None = None,
    note: str = "",
) -> dict[str, Any] | None:
    if not knowledge_point_id:
        return None
    student = _get_student_by_username(db, student_username)
    point = db.query(KnowledgePoint).filter(KnowledgePoint.id == knowledge_point_id).first()
    if not student or not point:
        return None
    result = apply_mastery_event(
        db,
        student_id=student.id,
        knowledge_point_id=point.id,
        source_type=source_type,
        source_id=source_id,
        difficulty=difficulty,
        answer_quality=answer_quality,
        used_hint=used_hint,
        attempt_count=attempt_count,
        score=score,
        max_score=max_score,
        is_correct=is_correct,
        note=note,
    )
    return {
        "event_id": result.event.id,
        "knowledge_point_id": point.id,
        "mastery_level": result.mastery.mastery_level,
        "mastery_delta": result.event.mastery_delta,
        "strategy": result.details,
    }


def _assignment_text(title: str, description: str, files: list[dict[str, Any]]) -> str:
    parts = [title or "", description or ""]
    for file in files:
        parts.append(str(file.get("filename", "")))
        file_text = _extract_text_from_file(str(file.get("path", "")))
        if file_text:
            parts.append(file_text)
    return "\n".join(parts).strip()


def _keyword_overlap_score(a: str, b: str) -> float:
    a_words = _normalize_keywords(a)
    b_words = _normalize_keywords(b)
    if not a_words or not b_words:
        return 0.0
    overlap = len(a_words & b_words)
    return overlap / max(1, min(len(a_words), len(b_words)))


def _knowledge_point_label(point: KnowledgePoint) -> str:
    return "\n".join([point.name or "", point.description or "", point.chapter.title if point.chapter else ""])


def _analyze_assignment_knowledge(
    db: Session,
    *,
    course_id: int | None,
    chapter_id: int | None,
    title: str,
    description: str,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    text = _assignment_text(title, description, files)
    query = db.query(KnowledgePoint)
    if course_id:
        query = query.filter(KnowledgePoint.course_id == course_id)
    if chapter_id:
        query = query.filter(
            (KnowledgePoint.chapter_id == chapter_id) | (KnowledgePoint.chapter_id.is_(None))
        )
    existing_points = query.order_by(KnowledgePoint.priority.desc()).all() if course_id else []

    links: list[dict[str, Any]] = []
    for point in existing_points:
        score = _keyword_overlap_score(text, _knowledge_point_label(point))
        name_hit = point.name and point.name in text
        if name_hit:
            score = max(score, 1.0)
        if score < 0.2:
            continue
        links.append(
            {
                "knowledge_point_id": point.id,
                "knowledge_point": point.name,
                "chapter_id": point.chapter_id,
                "chapter_title": point.chapter.title if point.chapter else "",
                "priority": point.priority,
                "is_confirmed": point.is_confirmed,
                "match_score": round(score, 3),
                "source": "existing",
            }
        )

    links.sort(key=lambda item: (-float(item["match_score"]), -int(item["priority"])))
    task_points = _split_task_points(title, description, [file.get("filename", "") for file in files])
    if text:
        task_points.extend(
            [
                part.strip()
                for part in re.split(r"[\n。；;！？!?]", text)
                if 4 <= len(part.strip()) <= 40
            ][:8]
        )

    seen_candidates: set[str] = set()
    candidates: list[dict[str, Any]] = []
    existing_names = {str(point.name).strip() for point in existing_points}
    for raw in task_points:
        name = raw.strip(" \t\r\n-:：,，.。")
        if len(name) < 4 or len(name) > 40:
            continue
        if name in seen_candidates or name in existing_names:
            continue
        if any(_keyword_overlap_score(name, link["knowledge_point"]) >= 0.6 for link in links):
            continue
        seen_candidates.add(name)
        candidates.append(
            {
                "candidate_id": f"cand_{uuid.uuid4().hex[:8]}",
                "name": name,
                "description": "由作业要求自动识别，待教师确认。",
                "chapter_id": chapter_id,
                "priority": 3,
                "status": "pending",
            }
        )
        if len(candidates) >= 6:
            break

    return {
        "text_excerpt": text[:1000],
        "knowledge_links": links[:8],
        "knowledge_candidates": candidates,
        "task_points": task_points[:8],
        "analyzed_at": time.time(),
    }


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
    submitted_file_text = "\n".join(
        text for text in (_extract_text_from_file(file.get("path", "")) for file in files) if text
    )
    full_answer_text = "\n".join([answer_text or "", submitted_file_text]).strip()
    assignment_text = "\n".join(
        [
            assignment.get("title", ""),
            assignment.get("description", ""),
            " ".join(item.get("name", "") for item in rubric_items),
            " ".join(link.get("knowledge_point", "") for link in assignment.get("knowledge_links", []) or []),
        ]
    )

    assignment_keywords = _normalize_keywords(assignment_text)
    answer_keywords = _normalize_keywords(full_answer_text)

    overlap = assignment_keywords.intersection(answer_keywords)
    relevance_ratio = 0.0
    if assignment_keywords:
        relevance_ratio = len(overlap) / len(assignment_keywords)

    text_len_score = min(1.0, len(full_answer_text.strip()) / 300)
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
    if len(full_answer_text.strip()) < 120:
        suggestions.append("补充关键过程、结果解释与结论，避免只写简短答案。")
    for dim in weak_dims[:2]:
        suggestions.append(f"围绕“{dim['name']}”补做 1-2 道同类练习并复盘。")
    if not suggestions:
        suggestions.append("整体完成较好，可尝试提升表达精炼度与反思深度。")

    summary = (
        f"相关性 {relevance_score} 分，总分 {total_score} 分。"
        f"已识别 {len(errors)} 个待改进点，建议按维度逐项优化。"
    )

    knowledge_results: list[dict[str, Any]] = []
    for link in assignment.get("knowledge_links", []) or []:
        kp_name = str(link.get("knowledge_point", "")).strip()
        if not kp_name:
            continue
        kp_score = _keyword_overlap_score(full_answer_text, kp_name)
        if kp_name in full_answer_text:
            kp_score = max(kp_score, 0.85)
        if kp_score >= 0.65:
            status = "correct"
            feedback = "该知识点在答案中体现较充分。"
        elif kp_score >= 0.35:
            status = "partial"
            feedback = "该知识点有部分体现，但还需要补充关键过程或解释。"
        else:
            status = "incorrect"
            feedback = "该知识点在答案中体现不足，建议加入错题本复盘。"
        knowledge_results.append(
            {
                "knowledge_point_id": link.get("knowledge_point_id"),
                "knowledge_point": kp_name,
                "chapter_title": link.get("chapter_title", ""),
                "score_ratio": round(max(0.0, min(1.0, kp_score)), 3),
                "status": status,
                "feedback": feedback,
            }
        )

    return {
        "generated_at": time.time(),
        "relevance_score": relevance_score,
        "total_score": total_score,
        "rubric_scores": rubric_scores,
        "knowledge_results": knowledge_results,
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
async def generate_rubric_draft(request: RubricDraftRequest, db: Session = Depends(get_db)):
    task_points = _split_task_points(
        title=request.title,
        description=request.description,
        file_names=request.file_names,
    )
    if request.course_id:
        query = db.query(KnowledgePoint).filter(KnowledgePoint.course_id == request.course_id)
        if request.chapter_id:
            query = query.filter(
                (KnowledgePoint.chapter_id == request.chapter_id)
                | (KnowledgePoint.chapter_id.is_(None))
            )
        for point in query.order_by(KnowledgePoint.priority.desc()).limit(6).all():
            if point.name not in task_points:
                task_points.append(point.name)
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
    course_id: int | None = Form(None),
    chapter_id: int | None = Form(None),
    rubric_json: str = Form("[]"),
    files: list[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
):
    store = get_assignment_review_store()
    assignment_id = f"asg_{uuid.uuid4().hex[:10]}"
    course = db.query(Course).filter(Course.id == course_id).first() if course_id else None
    teacher = _get_teacher_by_username(db, teacher_username)
    if course and teacher and course.teacher_id != teacher.id:
        raise HTTPException(status_code=403, detail="Course is not owned by this teacher")
    chapter = (
        db.query(CourseChapter)
        .filter(CourseChapter.id == chapter_id, CourseChapter.course_id == course_id)
        .first()
        if course_id and chapter_id
        else None
    )

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
    analysis = _analyze_assignment_knowledge(
        db,
        course_id=course.id if course else None,
        chapter_id=chapter.id if chapter else None,
        title=title,
        description=description,
        files=stored_files,
    )

    assignment = store.create_assignment(
        teacher_username=teacher_username,
        title=title,
        description=description,
        rubric_items=[item.model_dump() for item in rubric_items],
        files=stored_files,
        assignment_id=assignment_id,
        course_id=course.id if course else None,
        chapter_id=chapter.id if chapter else None,
        course_name=course.name if course else "",
        chapter_title=chapter.title if chapter else "",
        knowledge_links=analysis["knowledge_links"],
        knowledge_candidates=analysis["knowledge_candidates"],
        analysis=analysis,
    )
    return {"success": True, "assignment": assignment}


@router.post("/teacher/assignments/{assignment_id}/knowledge-candidates/confirm")
async def confirm_assignment_knowledge_candidates(
    assignment_id: str,
    request: ConfirmKnowledgeCandidatesRequest,
    db: Session = Depends(get_db),
):
    store = get_assignment_review_store()
    assignment = store.get_assignment_by_id(assignment_id)
    if not assignment or assignment.get("teacher_username") != request.teacher_username:
        raise HTTPException(status_code=404, detail="Assignment not found or not owned by teacher")
    teacher = _get_teacher_by_username(db, request.teacher_username)
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    course_id = assignment.get("course_id")
    if not course_id:
        raise HTTPException(status_code=400, detail="Assignment is not linked to a course")

    created_links = []
    for candidate in request.candidates:
        name = candidate.name.strip()
        if not name:
            continue
        chapter_id = candidate.chapter_id or assignment.get("chapter_id")
        existing = (
            db.query(KnowledgePoint)
            .filter(
                KnowledgePoint.course_id == course_id,
                KnowledgePoint.chapter_id == chapter_id,
                KnowledgePoint.name == name,
            )
            .first()
        )
        point = existing
        if not point:
            point = KnowledgePoint(
                course_id=course_id,
                chapter_id=chapter_id,
                created_by_teacher_id=teacher.id,
                name=name,
                description=candidate.description.strip(),
                priority=candidate.priority,
                source_type="assignment_question",
                source_ref=f"assignment:{assignment_id}",
                is_confirmed=True,
            )
            db.add(point)
            db.flush()
        created_links.append(
            {
                "knowledge_point_id": point.id,
                "knowledge_point": point.name,
                "chapter_id": point.chapter_id,
                "chapter_title": point.chapter.title if point.chapter else assignment.get("chapter_title", ""),
                "priority": point.priority,
                "is_confirmed": point.is_confirmed,
                "match_score": 1.0,
                "source": "confirmed_candidate",
            }
        )
    db.commit()

    links = assignment.get("knowledge_links", []) or []
    known_ids = {link.get("knowledge_point_id") for link in links}
    for link in created_links:
        if link.get("knowledge_point_id") not in known_ids:
            links.append(link)
    candidates = assignment.get("knowledge_candidates", []) or []
    confirmed_names = {candidate.name.strip() for candidate in request.candidates}
    for candidate in candidates:
        if candidate.get("name") in confirmed_names:
            candidate["status"] = "confirmed"
    updated = store.update_assignment_fields(
        assignment_id,
        request.teacher_username,
        {"knowledge_links": links, "knowledge_candidates": candidates},
    )
    return {"success": True, "assignment": updated, "created_links": created_links}


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
    db: Session = Depends(get_db),
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
    mastery_updates = []
    wrongbook_items = []
    for item in auto_review.get("knowledge_results", []) or []:
        kp_id = item.get("knowledge_point_id")
        status = item.get("status")
        is_correct = True if status == "correct" else False if status == "incorrect" else None
        update = _apply_optional_mastery_update(
            db,
            student_username=student_username,
            knowledge_point_id=kp_id,
            source_type="assignment_question",
            source_id=f"{submission['id']}:{kp_id}",
            score=float(item.get("score_ratio", 0.0)),
            max_score=1.0,
            is_correct=is_correct,
            difficulty="medium",
            answer_quality="partial" if status == "partial" else "wrong" if status == "incorrect" else None,
            note="作业自动评审后更新知识点掌握度",
        )
        if update:
            mastery_updates.append(update)
        if status == "incorrect":
            wrong = store.add_wrongbook_item(
                student_username=student_username,
                assignment_id=assignment_id,
                assignment_title=assignment.get("title", "作业审查"),
                feedback=item.get("feedback", "该知识点作业表现不足。"),
                error_type="作业知识点薄弱",
                knowledge_point=item.get("knowledge_point", ""),
                knowledge_point_id=kp_id,
                suggestion="回到课程中心复习该知识点，并在题目模块进行同知识点练习。",
                source_submission_id=submission["id"],
            )
            wrongbook_items.append(wrong)
    if mastery_updates:
        db.commit()
    auto_review["mastery_updates"] = mastery_updates
    auto_review["wrongbook_items"] = wrongbook_items
    updated_submission = store.update_submission_auto_review(submission["id"], auto_review) or submission
    return {"success": True, "submission": updated_submission, "auto_review": auto_review}


@router.post("/teacher/submissions/{submission_id}/review")
async def review_submission(
    submission_id: str,
    request: ReviewSubmissionRequest,
    db: Session = Depends(get_db),
):
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
    mastery_updates = []
    student_username = str(submission.get("student_username") or "")
    if student_username:
        for item in request.wrongbook_items:
            update = _apply_optional_mastery_update(
                db,
                student_username=student_username,
                knowledge_point_id=item.knowledge_point_id,
                source_type="assignment_question",
                source_id=submission_id,
                score=0,
                max_score=1,
                is_correct=False,
                difficulty="medium",
                answer_quality="wrong",
                note=item.feedback or "作业评审生成错题后自动更新掌握度",
            )
            if update:
                mastery_updates.append(update)
        if mastery_updates:
            db.commit()
    return {"success": True, "submission": submission, "mastery_updates": mastery_updates}


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


@router.post("/student/wrongbook/{item_id}/practice-result")
async def submit_wrongbook_practice_result(
    item_id: str,
    request: WrongbookPracticeResultRequest,
    db: Session = Depends(get_db),
):
    store = get_assignment_review_store()
    items = store.list_wrongbook_items(request.student_username)
    target = next((x for x in items if x.get("id") == item_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Wrongbook item not found")

    knowledge_point_id = request.knowledge_point_id or target.get("knowledge_point_id")
    update = _apply_optional_mastery_update(
        db,
        student_username=request.student_username,
        knowledge_point_id=knowledge_point_id,
        source_type="wrongbook_practice",
        source_id=request.source_id or item_id,
        score=request.score,
        max_score=request.max_score,
        is_correct=request.is_correct,
        difficulty=request.difficulty,
        answer_quality=request.answer_quality,
        used_hint=request.used_hint,
        attempt_count=request.attempt_count,
        note=request.note or "错题本练习后自动更新掌握度",
    )
    if update:
        db.commit()
    return {"success": True, "mastery_update": update}


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
        knowledge_point_id=request.knowledge_point_id,
        suggestion=request.suggestion,
        source_submission_id=request.source_submission_id,
    )
    return {"success": True, "item": item}
