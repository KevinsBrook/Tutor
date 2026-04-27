from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Literal
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.database import SessionLocal, get_db
from src.core.models import (
    Course,
    CourseChapter,
    CourseMaterial,
    KnowledgePoint,
    KnowledgeMasteryEvent,
    Student,
    StudentKnowledgeMastery,
    Teacher,
    User,
)
from src.utils.document_validator import DocumentValidator
from src.api.routers.knowledge import (
    _kb_base_dir,
    get_kb_manager,
    get_llm_config,
    KnowledgeBaseInitializer,
    ProgressStage,
    ProgressTracker,
    _build_graph_payload,
    get_provider_supported_extensions,
    is_knowledge_base_initialized,
    normalize_rag_provider,
    run_initialization_task,
    run_upload_processing_task,
    validate_rag_provider_files,
    _safe_read_json,
)
from src.services.mastery import apply_mastery_event

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COURSE_MATERIAL_ROOT = PROJECT_ROOT / "data" / "user" / "course_materials"
MASTERY_REMINDER_FILE = PROJECT_ROOT / "data" / "user" / "mastery_reminders.json"
COURSE_MATERIAL_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".ppt",
    ".pptx",
    ".doc",
    ".docx",
    ".txt",
    ".md",
    ".rtf",
    ".html",
    ".htm",
}

CourseStatus = Literal["active", "archived"]
MaterialScope = Literal["chapter", "course_public"]
CourseMaterialSource = Literal[
    "teacher_material",
    "student_note",
    "assignment_question",
    "wrongbook_practice",
]


class CourseCreateRequest(BaseModel):
    teacher_username: str
    name: str
    description: str = ""


class CourseUpdateRequest(BaseModel):
    teacher_username: str
    name: str | None = None
    description: str | None = None
    status: CourseStatus | None = None


class ChapterCreateRequest(BaseModel):
    teacher_username: str
    title: str
    description: str = ""
    order_index: int = Field(default=1, ge=1)


class ChapterUpdateRequest(BaseModel):
    teacher_username: str
    title: str | None = None
    description: str | None = None
    order_index: int | None = Field(default=None, ge=1)


class MaterialCreateRequest(BaseModel):
    uploader_username: str
    chapter_id: int | None = None
    title: str
    description: str = ""
    source_type: CourseMaterialSource = "teacher_material"
    original_filename: str | None = None
    file_path: str | None = None
    file_type: str | None = None
    kb_name: str | None = None
    rag_provider: str | None = None
    parse_status: str = "pending"


class MaterialUpdateRequest(BaseModel):
    operator_username: str
    title: str | None = None
    description: str | None = None
    chapter_id: int | None = None
    parse_status: str | None = None
    rag_provider: str | None = None


class KnowledgePointCreateRequest(BaseModel):
    teacher_username: str
    chapter_id: int | None = None
    source_material_id: int | None = None
    name: str
    description: str = ""
    priority: int = Field(default=3, ge=1, le=5)
    source_type: str = "teacher_material"
    source_ref: str = ""
    is_confirmed: bool = False


class KnowledgePointUpdateRequest(BaseModel):
    teacher_username: str
    name: str | None = None
    description: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    is_confirmed: bool | None = None


class MasteryEventCreateRequest(BaseModel):
    student_username: str
    source_type: Literal[
        "question_practice",
        "assignment_question",
        "wrongbook_practice",
        "manual",
    ] = "manual"
    source_id: str | None = None
    score: float | None = None
    max_score: float | None = None
    is_correct: bool | None = None
    mastery_delta: float | None = Field(default=None, ge=-1.0, le=1.0)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    answer_quality: Literal[
        "independent",
        "hinted",
        "multi_attempt",
        "partial",
        "wrong",
    ] | None = None
    used_hint: bool = False
    attempt_count: int | None = Field(default=None, ge=1, le=20)
    note: str = ""


class MasteryEventBatchItem(BaseModel):
    knowledge_point_id: int
    source_type: Literal[
        "question_practice",
        "assignment_question",
        "wrongbook_practice",
        "manual",
    ] = "question_practice"
    source_id: str | None = None
    score: float | None = None
    max_score: float | None = None
    is_correct: bool | None = None
    mastery_delta: float | None = Field(default=None, ge=-1.0, le=1.0)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    answer_quality: Literal[
        "independent",
        "hinted",
        "multi_attempt",
        "partial",
        "wrong",
    ] | None = None
    used_hint: bool = False
    attempt_count: int | None = Field(default=None, ge=1, le=20)
    note: str = ""


class MasteryEventBatchCreateRequest(BaseModel):
    student_username: str
    events: list[MasteryEventBatchItem]


class MasteryReminderCreateRequest(BaseModel):
    teacher_username: str
    student_username: str
    knowledge_point_id: int
    content: str


def _get_teacher_by_username(db: Session, username: str) -> Teacher:
    user = db.query(User).filter(User.username == username, User.role == "teacher").first()
    if not user:
        raise HTTPException(status_code=404, detail="未找到教师账号")
    teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="未找到教师档案")
    return teacher


def _get_student_by_username(db: Session, username: str) -> Student:
    user = db.query(User).filter(User.username == username, User.role == "student").first()
    if not user:
        raise HTTPException(status_code=404, detail="未找到学生账号")
    student = db.query(Student).filter(Student.user_id == user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="未找到学生档案")
    return student


def _get_user_by_username(db: Session, username: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="未找到用户")
    return user


def _get_course(db: Session, course_id: int) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course


def _get_chapter(db: Session, chapter_id: int) -> CourseChapter:
    chapter = db.query(CourseChapter).filter(CourseChapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    return chapter


def _get_course_chapter(db: Session, course_id: int, chapter_id: int) -> CourseChapter:
    chapter = (
        db.query(CourseChapter)
        .filter(CourseChapter.id == chapter_id, CourseChapter.course_id == course_id)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在或不属于该课程")
    return chapter


def _get_material(db: Session, material_id: int) -> CourseMaterial:
    material = db.query(CourseMaterial).filter(CourseMaterial.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="资料不存在")
    return material


def _get_knowledge_point(db: Session, point_id: int) -> KnowledgePoint:
    point = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="知识点不存在")
    return point


def _ensure_teacher_owns_course(teacher: Teacher, course: Course) -> None:
    if course.teacher_id != teacher.id:
        raise HTTPException(status_code=403, detail="只能管理自己创建的课程")


def _ensure_material_operator(db: Session, username: str, material: CourseMaterial) -> User:
    user = _get_user_by_username(db, username)
    if user.role == "teacher":
        teacher = _get_teacher_by_username(db, username)
        _ensure_teacher_owns_course(teacher, material.course)
        return user
    if material.source_type == "student_note" and material.uploader_user_id == user.id:
        return user
    raise HTTPException(status_code=403, detail="无权管理该资料")


def _commit_or_conflict(db: Session, conflict_detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=conflict_detail) from exc


def _delete_knowledge_points_with_records(db: Session, point_ids: list[int]) -> None:
    if not point_ids:
        return
    db.query(StudentKnowledgeMastery).filter(
        StudentKnowledgeMastery.knowledge_point_id.in_(point_ids),
    ).delete(synchronize_session=False)
    db.query(KnowledgeMasteryEvent).filter(
        KnowledgeMasteryEvent.knowledge_point_id.in_(point_ids),
    ).delete(synchronize_session=False)
    db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).delete(
        synchronize_session=False,
    )


def _delete_course_children(db: Session, course_id: int) -> None:
    point_ids = [
        point_id
        for (point_id,) in db.query(KnowledgePoint.id)
        .filter(KnowledgePoint.course_id == course_id)
        .all()
    ]
    _delete_knowledge_points_with_records(db, point_ids)
    db.query(CourseMaterial).filter(CourseMaterial.course_id == course_id).delete(
        synchronize_session=False,
    )
    db.query(CourseChapter).filter(CourseChapter.course_id == course_id).delete(
        synchronize_session=False,
    )


def _delete_chapter_children(db: Session, chapter_id: int) -> None:
    point_ids = [
        point_id
        for (point_id,) in db.query(KnowledgePoint.id)
        .filter(KnowledgePoint.chapter_id == chapter_id)
        .all()
    ]
    _delete_knowledge_points_with_records(db, point_ids)
    db.query(CourseMaterial).filter(CourseMaterial.chapter_id == chapter_id).delete(
        synchronize_session=False,
    )


def _calculate_mastery_delta(request: MasteryEventCreateRequest) -> float:
    if request.mastery_delta is not None:
        return request.mastery_delta
    if request.is_correct is not None:
        return 0.08 if request.is_correct else -0.06
    if request.score is not None and request.max_score and request.max_score > 0:
        ratio = max(0.0, min(1.0, request.score / request.max_score))
        return (ratio - 0.5) * 0.16
    return 0.0


def _auto_kb_name(course_id: int, chapter_id: int | None, scope: MaterialScope) -> str:
    if scope == "course_public":
        return f"course_{course_id}_public"
    return f"course_{course_id}_chapter_{chapter_id}"


def _write_course_kb_metadata(
    kb_name: str,
    material_id: int,
    display_name: str,
    course_id: int,
    chapter_id: int | None,
    source_type: str,
    rag_provider: str,
) -> None:
    """Mark the hidden RAG index behind course material as course-scoped."""
    kb_dir = _kb_base_dir / kb_name
    metadata_file = kb_dir / "metadata.json"
    metadata: dict = {}
    if metadata_file.exists():
        try:
            with open(metadata_file, encoding="utf-8") as fp:
                metadata = json.load(fp)
        except Exception:
            metadata = {}

    metadata.update(
        {
            "name": kb_name,
            "display_name": display_name,
            "description": f"课程资料：{display_name}",
            "scope": "course_material",
            "course_id": course_id,
            "chapter_id": chapter_id,
            "material_id": material_id,
            "source_type": source_type,
            "rag_provider": rag_provider,
            "last_updated": datetime.utcnow().isoformat(),
        }
    )
    kb_dir.mkdir(parents=True, exist_ok=True)
    with open(metadata_file, "w", encoding="utf-8") as fp:
        json.dump(metadata, fp, indent=2, ensure_ascii=False)

    manager = get_kb_manager()
    manager.config = manager._load_config()
    kb_config = manager.config.setdefault("knowledge_bases", {}).setdefault(
        kb_name,
        {"path": kb_name},
    )
    kb_config.update(
        {
            "description": display_name,
            "display_name": display_name,
            "scope": "course_material",
            "course_id": course_id,
            "chapter_id": chapter_id,
            "material_id": material_id,
            "source_type": source_type,
            "rag_provider": rag_provider,
        }
    )
    manager._save_config()


def _save_course_material_file(
    file: UploadFile,
    course_id: int,
    chapter_id: int | None,
    source_type: str,
    scope: MaterialScope,
    allowed_extensions: set[str] | None = None,
) -> tuple[str, str, int]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    filename = DocumentValidator.validate_upload_safety(
        file.filename,
        None,
        allowed_extensions or COURSE_MATERIAL_ALLOWED_EXTENSIONS,
    )
    folder_key = f"chapter_{chapter_id}" if chapter_id else scope
    folder = COURSE_MATERIAL_ROOT / str(course_id) / folder_key / source_type
    folder.mkdir(parents=True, exist_ok=True)

    unique_prefix = uuid.uuid4().hex[:10]
    target = folder / f"{unique_prefix}_{filename}"
    with open(target, "wb") as out:
        shutil.copyfileobj(file.file, out)

    return str(target), Path(filename).suffix.lower(), target.stat().st_size


def _set_material_parse_status(material_id: int, status: str) -> None:
    db = SessionLocal()
    try:
        material = db.query(CourseMaterial).filter(CourseMaterial.id == material_id).first()
        if material:
            material.parse_status = status
            material.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _sync_material_knowledge_points(material_id: int, limit: int = 24) -> int:
    db = SessionLocal()
    try:
        material = db.query(CourseMaterial).filter(CourseMaterial.id == material_id).first()
        if not material or not material.kb_name:
            return 0

        kb_dir = _kb_base_dir / material.kb_name
        rag_storage_dir = kb_dir / "rag_storage"
        entities_file = rag_storage_dir / "kv_store_full_entities.json"
        relations_file = rag_storage_dir / "kv_store_full_relations.json"
        if not entities_file.exists() or not relations_file.exists():
            return 0

        graph_payload = _build_graph_payload(
            entities_raw=_safe_read_json(entities_file),
            relations_raw=_safe_read_json(relations_file),
            max_nodes=limit * 3,
            max_edges=limit * 8,
            min_degree=0,
            filter_noise=True,
        )
        nodes = sorted(
            graph_payload.get("nodes", []),
            key=lambda node: (int(node.get("degree") or 0), str(node.get("label") or "")),
            reverse=True,
        )

        existing_names = {
            str(name).strip().lower()
            for (name,) in db.query(KnowledgePoint.name)
            .filter(
                KnowledgePoint.course_id == material.course_id,
                KnowledgePoint.chapter_id == material.chapter_id,
            )
            .all()
        }
        created = 0
        for node in nodes:
            label = str(node.get("label") or node.get("id") or "").strip()
            if not label or len(label) > 80 or label.lower() in existing_names:
                continue
            degree = int(node.get("degree") or 0)
            point = KnowledgePoint(
                course_id=material.course_id,
                chapter_id=material.chapter_id,
                source_material_id=material.id,
                created_by_teacher_id=material.course.teacher_id if material.course else None,
                name=label,
                description=str(node.get("description") or ""),
                priority=4 if degree >= 5 else 3,
                source_type=material.source_type,
                source_ref=f"kb:{material.kb_name};node:{node.get('id') or label}",
                is_confirmed=False,
            )
            db.add(point)
            existing_names.add(label.lower())
            created += 1
            if created >= limit:
                break

        if created:
            db.commit()
        return created
    except Exception:
        db.rollback()
        return 0
    finally:
        db.close()


async def _run_course_material_initialization_task(
    material_id: int,
    initializer: KnowledgeBaseInitializer,
) -> None:
    _set_material_parse_status(material_id, "parsing")
    await run_initialization_task(initializer)
    if is_knowledge_base_initialized(initializer.kb_name):
        _sync_material_knowledge_points(material_id)
    _set_material_parse_status(
        material_id,
        "parsed" if is_knowledge_base_initialized(initializer.kb_name) else "failed",
    )


async def _run_course_material_upload_task(
    material_id: int,
    kb_name: str,
    base_dir: str,
    api_key: str,
    base_url: str,
    uploaded_file_paths: list[str],
    rag_provider: str,
) -> None:
    _set_material_parse_status(material_id, "parsing")
    await run_upload_processing_task(
        kb_name=kb_name,
        base_dir=base_dir,
        api_key=api_key,
        base_url=base_url,
        uploaded_file_paths=uploaded_file_paths,
        rag_provider=rag_provider,
    )
    if is_knowledge_base_initialized(kb_name):
        _sync_material_knowledge_points(material_id)
    _set_material_parse_status(
        material_id,
        "parsed" if is_knowledge_base_initialized(kb_name) else "failed",
    )


def _enqueue_course_material_rag(
    background_tasks: BackgroundTasks,
    material_id: int,
    kb_name: str,
    file_path: str,
    rag_provider: str | None,
    display_name: str,
    course_id: int,
    chapter_id: int | None,
    source_type: str,
) -> str:
    manager = get_kb_manager()
    llm_config = get_llm_config()
    provider = normalize_rag_provider(rag_provider)

    if kb_name not in manager.list_knowledge_bases() or not is_knowledge_base_initialized(kb_name):
        manager.update_kb_status(
            name=kb_name,
            status="initializing",
            progress={
                "stage": "initializing",
                "message": "Initializing course knowledge base...",
                "percent": 0,
                "current": 0,
                "total": 1,
            },
        )
        manager.config = manager._load_config()
        if kb_name in manager.config.get("knowledge_bases", {}):
            manager.config["knowledge_bases"][kb_name]["rag_provider"] = provider
            manager._save_config()

        progress_tracker = ProgressTracker(kb_name, _kb_base_dir)
        initializer = KnowledgeBaseInitializer(
            kb_name=kb_name,
            base_dir=str(_kb_base_dir),
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            progress_tracker=progress_tracker,
            rag_provider=provider,
        )
        initializer.create_directory_structure()
        if kb_name not in manager.list_knowledge_bases():
            initializer._register_to_config()
        _write_course_kb_metadata(
            kb_name=kb_name,
            material_id=material_id,
            display_name=display_name,
            course_id=course_id,
            chapter_id=chapter_id,
            source_type=source_type,
            rag_provider=provider,
        )

        target = initializer.raw_dir / Path(file_path).name
        if not target.exists():
            shutil.copyfile(file_path, target)

        progress_tracker.update(
            ProgressStage.PROCESSING_DOCUMENTS,
            "Saved course material, preparing to process...",
            current=0,
            total=1,
        )
        background_tasks.add_task(
            _run_course_material_initialization_task,
            material_id,
            initializer,
        )
    else:
        _write_course_kb_metadata(
            kb_name=kb_name,
            material_id=material_id,
            display_name=display_name,
            course_id=course_id,
            chapter_id=chapter_id,
            source_type=source_type,
            rag_provider=provider,
        )
        background_tasks.add_task(
            _run_course_material_upload_task,
            material_id,
            kb_name,
            str(_kb_base_dir),
            llm_config.api_key,
            llm_config.base_url,
            [file_path],
            provider,
        )

    return "parsing"


def _course_payload(course: Course) -> dict:
    return {
        "id": course.id,
        "teacher_id": course.teacher_id,
        "teacher_name": course.teacher.real_name if course.teacher else "",
        "name": course.name,
        "description": course.description or "",
        "status": course.status,
        "chapter_count": len(course.chapters or []),
        "material_count": len(course.materials or []),
        "knowledge_point_count": len(course.knowledge_points or []),
        "created_at": course.created_at,
        "updated_at": course.updated_at,
    }


def _chapter_payload(chapter: CourseChapter) -> dict:
    return {
        "id": chapter.id,
        "course_id": chapter.course_id,
        "title": chapter.title,
        "description": chapter.description or "",
        "order_index": chapter.order_index,
        "material_count": len(chapter.materials or []),
        "knowledge_point_count": len(chapter.knowledge_points or []),
        "created_at": chapter.created_at,
        "updated_at": chapter.updated_at,
    }


def _material_payload(material: CourseMaterial) -> dict:
    return {
        "id": material.id,
        "course_id": material.course_id,
        "chapter_id": material.chapter_id,
        "chapter_title": material.chapter.title if material.chapter else "",
        "uploader_user_id": material.uploader_user_id,
        "student_uploader_id": material.student_uploader_id,
        "title": material.title,
        "display_name": material.title or material.original_filename or material.kb_name,
        "description": material.description or "",
        "source_type": material.source_type,
        "original_filename": material.original_filename,
        "file_path": material.file_path,
        "file_type": material.file_type,
        "kb_name": material.kb_name,
        "rag_provider": material.rag_provider,
        "parse_status": material.parse_status,
        "created_at": material.created_at,
        "updated_at": material.updated_at,
    }


def _knowledge_point_payload(
    point: KnowledgePoint,
    mastery: StudentKnowledgeMastery | None = None,
) -> dict:
    payload = {
        "id": point.id,
        "course_id": point.course_id,
        "chapter_id": point.chapter_id,
        "chapter_title": point.chapter.title if point.chapter else "",
        "source_material_id": point.source_material_id,
        "source_material_title": point.source_material.title if point.source_material else "",
        "source_material_filename": (
            point.source_material.original_filename if point.source_material else ""
        ),
        "name": point.name,
        "description": point.description or "",
        "priority": point.priority,
        "source_type": point.source_type,
        "source_ref": point.source_ref or "",
        "is_confirmed": point.is_confirmed,
        "created_at": point.created_at,
        "updated_at": point.updated_at,
    }
    if mastery:
        payload["mastery"] = {
            "mastery_level": mastery.mastery_level,
            "correct_count": mastery.correct_count,
            "wrong_count": mastery.wrong_count,
            "practice_count": mastery.practice_count,
            "last_practiced_at": mastery.last_practiced_at,
        }
    else:
        payload["mastery"] = {
            "mastery_level": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "practice_count": 0,
            "last_practiced_at": None,
        }
    return payload


def _mastery_band(level: float) -> str:
    if level >= 0.8:
        return "mastered"
    if level >= 0.6:
        return "basic"
    if level >= 0.3:
        return "forming"
    return "weak"


def _point_recommendation(point: KnowledgePoint, mastery_level: float) -> str:
    if mastery_level <= 0:
        return "先完成 2-3 道基础题，建立第一批掌握证据。"
    if mastery_level < 0.3:
        return "建议先做低难度题，答对后再进入变式训练。"
    if mastery_level < 0.6:
        return "建议做同知识点变式题，重点复盘错误原因。"
    if mastery_level < 0.8:
        return "建议补 1-2 道中高难度题，确认是否稳定掌握。"
    return "已基本掌握，可安排迁移应用或综合题。"


def _mastery_rows_for_student(
    db: Session,
    *,
    student: Student,
    courses: list[Course],
    confirmed_only: bool = True,
) -> tuple[list[dict], dict[int, StudentKnowledgeMastery]]:
    course_ids = [course.id for course in courses]
    if not course_ids:
        return [], {}

    point_query = db.query(KnowledgePoint).filter(KnowledgePoint.course_id.in_(course_ids))
    if confirmed_only:
        point_query = point_query.filter(KnowledgePoint.is_confirmed.is_(True))
    points = (
        point_query.order_by(
            KnowledgePoint.course_id.asc(),
            KnowledgePoint.priority.desc(),
            KnowledgePoint.created_at.asc(),
        )
        .all()
    )
    if not points:
        return [], {}

    records = (
        db.query(StudentKnowledgeMastery)
        .filter(
            StudentKnowledgeMastery.student_id == student.id,
            StudentKnowledgeMastery.knowledge_point_id.in_([point.id for point in points]),
        )
        .all()
    )
    record_map = {record.knowledge_point_id: record for record in records}
    rows = []
    for point in points:
        record = record_map.get(point.id)
        level = float(record.mastery_level or 0.0) if record else 0.0
        rows.append(
            {
                "knowledge_point": _knowledge_point_payload(point, record),
                "course_id": point.course_id,
                "course_name": point.course.name if point.course else "",
                "chapter_id": point.chapter_id,
                "chapter_title": point.chapter.title if point.chapter else "公共资料",
                "mastery_level": round(level, 4),
                "mastery_percent": round(level * 100, 1),
                "band": _mastery_band(level),
                "priority": int(point.priority or 3),
                "practice_count": int(record.practice_count or 0) if record else 0,
                "correct_count": int(record.correct_count or 0) if record else 0,
                "wrong_count": int(record.wrong_count or 0) if record else 0,
                "last_practiced_at": record.last_practiced_at if record else None,
                "recommendation": _point_recommendation(point, level),
            }
        )
    return rows, record_map


def _summarize_mastery_rows(rows: list[dict]) -> dict:
    total = len(rows)
    if not total:
        return {
            "knowledge_point_count": 0,
            "mastered_count": 0,
            "basic_count": 0,
            "forming_count": 0,
            "weak_count": 0,
            "unpracticed_count": 0,
            "average_mastery": 0,
        }
    return {
        "knowledge_point_count": total,
        "mastered_count": len([row for row in rows if row["mastery_level"] >= 0.8]),
        "basic_count": len([row for row in rows if 0.6 <= row["mastery_level"] < 0.8]),
        "forming_count": len([row for row in rows if 0.3 <= row["mastery_level"] < 0.6]),
        "weak_count": len([row for row in rows if row["mastery_level"] < 0.3]),
        "unpracticed_count": len([row for row in rows if row["practice_count"] == 0]),
        "average_mastery": round(
            sum(float(row["mastery_level"]) for row in rows) / total,
            4,
        ),
    }


def _group_student_profile(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    course_map: dict[int, dict] = {}
    chapter_map: dict[str, dict] = {}
    for row in rows:
        course = course_map.setdefault(
            row["course_id"],
            {
                "course_id": row["course_id"],
                "course_name": row["course_name"],
                "rows": [],
            },
        )
        course["rows"].append(row)

        chapter_key = f"{row['course_id']}:{row['chapter_id'] or 'public'}"
        chapter = chapter_map.setdefault(
            chapter_key,
            {
                "course_id": row["course_id"],
                "course_name": row["course_name"],
                "chapter_id": row["chapter_id"],
                "chapter_title": row["chapter_title"],
                "rows": [],
            },
        )
        chapter["rows"].append(row)

    course_cards = []
    for item in course_map.values():
        item_rows = item.pop("rows")
        weak_points = sorted(
            [row for row in item_rows if row["mastery_level"] < 0.6],
            key=lambda row: (-row["priority"], row["mastery_level"]),
        )[:3]
        course_cards.append(
            {
                **item,
                "summary": _summarize_mastery_rows(item_rows),
                "weak_points": weak_points,
            }
        )

    chapter_cards = []
    for item in chapter_map.values():
        item_rows = item.pop("rows")
        chapter_cards.append({**item, "summary": _summarize_mastery_rows(item_rows)})

    course_cards.sort(key=lambda item: item["course_name"])
    chapter_cards.sort(key=lambda item: (item["course_name"], item["chapter_title"]))
    return course_cards, chapter_cards


def _filter_mastery_rows(
    rows: list[dict],
    *,
    course_id: int | None = None,
    chapter_id: int | None = None,
    priority: int | None = None,
) -> list[dict]:
    filtered = rows
    if course_id:
        filtered = [row for row in filtered if row["course_id"] == course_id]
    if chapter_id:
        filtered = [row for row in filtered if row["chapter_id"] == chapter_id]
    if priority:
        filtered = [row for row in filtered if row["priority"] == priority]
    return filtered


def _wrongbook_counts_by_knowledge_point(student_username: str) -> dict[int, int]:
    try:
        from src.api.utils.assignment_review_store import get_assignment_review_store

        items = get_assignment_review_store().list_wrongbook_items(student_username)
    except Exception:
        return {}

    counts: dict[int, int] = {}
    for item in items:
        point_id = item.get("knowledge_point_id")
        if point_id is None:
            continue
        try:
            point_key = int(point_id)
        except (TypeError, ValueError):
            continue
        counts[point_key] = counts.get(point_key, 0) + 1
    return counts


def _related_materials_for_point(db: Session, point: KnowledgePoint, limit: int = 4) -> list[dict]:
    query = db.query(CourseMaterial).filter(CourseMaterial.course_id == point.course_id)
    if point.source_material_id:
        materials = (
            query.filter(CourseMaterial.id == point.source_material_id)
            .order_by(CourseMaterial.created_at.desc())
            .limit(limit)
            .all()
        )
    elif point.chapter_id:
        materials = (
            query.filter(CourseMaterial.chapter_id == point.chapter_id)
            .order_by(CourseMaterial.created_at.desc())
            .limit(limit)
            .all()
        )
    else:
        materials = query.order_by(CourseMaterial.created_at.desc()).limit(limit).all()
    return [_material_payload(material) for material in materials]


def _enrich_mastery_row(
    db: Session,
    row: dict,
    *,
    wrongbook_counts: dict[int, int],
    include_materials: bool = False,
) -> dict:
    point_payload = row.get("knowledge_point") or {}
    point_id = int(point_payload.get("id") or 0)
    enriched = {
        **row,
        "wrongbook_count": wrongbook_counts.get(point_id, 0),
    }
    if include_materials and point_id:
        point = db.query(KnowledgePoint).filter(KnowledgePoint.id == point_id).first()
        enriched["related_materials"] = (
            _related_materials_for_point(db, point) if point else []
        )
    return enriched


def _read_mastery_reminders() -> list[dict]:
    if not MASTERY_REMINDER_FILE.exists():
        return []
    try:
        with open(MASTERY_REMINDER_FILE, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []
    reminders = payload.get("reminders", []) if isinstance(payload, dict) else []
    return reminders if isinstance(reminders, list) else []


def _write_mastery_reminders(reminders: list[dict]) -> None:
    MASTERY_REMINDER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MASTERY_REMINDER_FILE, "w", encoding="utf-8") as file:
        json.dump({"reminders": reminders}, file, ensure_ascii=False, indent=2)


def _student_reminders(student_username: str) -> list[dict]:
    reminders = [
        reminder
        for reminder in _read_mastery_reminders()
        if reminder.get("student_username") == student_username
    ]
    reminders.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return reminders


@router.get("/mastery-page/student")
async def get_student_mastery_page(
    student_username: str,
    course_id: int | None = None,
    chapter_id: int | None = None,
    priority: int | None = None,
    db: Session = Depends(get_db),
):
    student = _get_student_by_username(db, student_username)
    all_courses = (
        db.query(Course).filter(Course.status == "active").order_by(Course.created_at.desc()).all()
    )
    courses = all_courses
    if course_id:
        courses = [course for course in all_courses if course.id == course_id]
        if not courses:
            raise HTTPException(status_code=404, detail="Course not found")

    rows, _ = _mastery_rows_for_student(db, student=student, courses=courses)
    filtered_rows = _filter_mastery_rows(
        rows,
        course_id=course_id,
        chapter_id=chapter_id,
        priority=priority,
    )
    wrongbook_counts = _wrongbook_counts_by_knowledge_point(student_username)
    enriched_rows = [
        _enrich_mastery_row(
            db,
            row,
            wrongbook_counts=wrongbook_counts,
            include_materials=True,
        )
        for row in filtered_rows
    ]

    chapters = [
        _chapter_payload(chapter)
        for course in all_courses
        for chapter in sorted(course.chapters or [], key=lambda item: item.order_index)
    ]

    return {
        "student": {
            "id": student.id,
            "username": student.user.username if student.user else student_username,
            "real_name": student.real_name,
            "student_no": student.student_no,
            "class_name": student.class_name,
            "grade_name": student.grade_name,
            "major": student.major,
        },
        "courses": [_course_payload(course) for course in all_courses],
        "chapters": chapters,
        "summary": _summarize_mastery_rows(filtered_rows),
        "knowledge_points": enriched_rows,
        "reminders": _student_reminders(student_username),
    }


@router.get("/mastery-page/teacher")
async def get_teacher_mastery_page(
    teacher_username: str,
    course_id: int | None = None,
    chapter_id: int | None = None,
    priority: int | None = None,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, teacher_username)
    all_courses = (
        db.query(Course)
        .filter(Course.teacher_id == teacher.id)
        .order_by(Course.created_at.desc())
        .all()
    )
    courses = all_courses
    if course_id:
        courses = [course for course in all_courses if course.id == course_id]
        if not courses:
            raise HTTPException(status_code=404, detail="Course not found")

    chapters = [
        _chapter_payload(chapter)
        for course in all_courses
        for chapter in sorted(course.chapters or [], key=lambda item: item.order_index)
    ]
    students = db.query(Student).order_by(Student.class_name.asc(), Student.real_name.asc()).all()

    matrix_rows: list[dict] = []
    aggregate: dict[int, dict] = {}
    for student in students:
        username = student.user.username if student.user else ""
        rows, _ = _mastery_rows_for_student(db, student=student, courses=courses)
        filtered_rows = _filter_mastery_rows(
            rows,
            course_id=course_id,
            chapter_id=chapter_id,
            priority=priority,
        )
        wrongbook_counts = _wrongbook_counts_by_knowledge_point(username) if username else {}
        for row in filtered_rows:
            point = row["knowledge_point"]
            point_id = int(point["id"])
            enriched = _enrich_mastery_row(db, row, wrongbook_counts=wrongbook_counts)
            matrix_rows.append(
                {
                    **enriched,
                    "student": {
                        "id": student.id,
                        "username": username,
                        "real_name": student.real_name,
                        "student_no": student.student_no,
                        "class_name": student.class_name,
                        "grade_name": student.grade_name,
                        "major": student.major,
                    },
                }
            )
            stats = aggregate.setdefault(
                point_id,
                {
                    "knowledge_point": point,
                    "course_id": row["course_id"],
                    "course_name": row["course_name"],
                    "chapter_id": row["chapter_id"],
                    "chapter_title": row["chapter_title"],
                    "priority": row["priority"],
                    "levels": [],
                    "weak_count": 0,
                    "unpracticed_count": 0,
                    "wrongbook_count": 0,
                },
            )
            stats["levels"].append(float(row["mastery_level"]))
            if row["mastery_level"] < 0.6:
                stats["weak_count"] += 1
            if row["practice_count"] == 0:
                stats["unpracticed_count"] += 1
            stats["wrongbook_count"] += wrongbook_counts.get(point_id, 0)

    weak_knowledge_points = []
    for stats in aggregate.values():
        levels = stats.pop("levels")
        average = sum(levels) / len(levels) if levels else 0
        weak_knowledge_points.append(
            {
                **stats,
                "average_mastery": round(average, 4),
                "mastery_percent": round(average * 100, 1),
                "student_count": len(levels),
            }
        )
    weak_knowledge_points.sort(
        key=lambda item: (
            item["average_mastery"],
            -item["weak_count"],
            -item["priority"],
        )
    )

    lagging_students = sorted(
        [
            row
            for row in matrix_rows
            if row["mastery_level"] < 0.6 or row["wrongbook_count"] > 0
        ],
        key=lambda row: (
            row["mastery_level"],
            -row["wrongbook_count"],
            -row["priority"],
        ),
    )[:30]

    return {
        "teacher": {
            "id": teacher.id,
            "username": teacher.user.username if teacher.user else teacher_username,
            "real_name": teacher.real_name,
            "department": teacher.department,
        },
        "courses": [_course_payload(course) for course in all_courses],
        "chapters": chapters,
        "summary": {
            **_summarize_mastery_rows(matrix_rows),
            "student_count": len(students),
            "course_count": len(courses),
        },
        "knowledge_points": list(aggregate.values()),
        "matrix_rows": matrix_rows,
        "weak_knowledge_points": weak_knowledge_points[:20],
        "lagging_students": lagging_students,
        "students": [
            {
                "id": student.id,
                "username": student.user.username if student.user else "",
                "real_name": student.real_name,
                "student_no": student.student_no,
                "class_name": student.class_name,
            }
            for student in students
        ],
    }


@router.get("/mastery-reminders/student")
async def list_student_mastery_reminders(student_username: str):
    return {"reminders": _student_reminders(student_username)}


@router.post("/mastery-reminders")
async def create_mastery_reminder(
    request: MasteryReminderCreateRequest,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, request.teacher_username)
    student = _get_student_by_username(db, request.student_username)
    point = _get_knowledge_point(db, request.knowledge_point_id)
    _ensure_teacher_owns_course(teacher, point.course)
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Reminder content is required")

    reminders = _read_mastery_reminders()
    reminder = {
        "id": uuid.uuid4().hex[:12],
        "teacher_username": request.teacher_username,
        "teacher_name": teacher.real_name,
        "student_username": request.student_username,
        "student_name": student.real_name,
        "knowledge_point_id": point.id,
        "knowledge_point_name": point.name,
        "course_id": point.course_id,
        "course_name": point.course.name if point.course else "",
        "chapter_id": point.chapter_id,
        "chapter_title": point.chapter.title if point.chapter else "",
        "content": content,
        "created_at": datetime.utcnow().isoformat(),
        "read": False,
    }
    reminders.append(reminder)
    _write_mastery_reminders(reminders)
    return {"success": True, "reminder": reminder}


@router.post("/mastery-reminders/{reminder_id}/read")
async def mark_mastery_reminder_read(reminder_id: str, student_username: str):
    reminders = _read_mastery_reminders()
    updated = None
    for reminder in reminders:
        if reminder.get("id") != reminder_id:
            continue
        if reminder.get("student_username") != student_username:
            raise HTTPException(status_code=403, detail="Cannot update this reminder")
        reminder["read"] = True
        updated = reminder
        break
    if not updated:
        raise HTTPException(status_code=404, detail="Reminder not found")
    _write_mastery_reminders(reminders)
    return {"success": True, "reminder": updated}


@router.get("")
async def list_courses(teacher_username: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Course)
    if teacher_username:
        teacher = _get_teacher_by_username(db, teacher_username)
        query = query.filter(Course.teacher_id == teacher.id)
    courses = query.order_by(Course.created_at.desc()).all()
    return {"courses": [_course_payload(course) for course in courses], "total": len(courses)}


@router.get("/learning-profile")
async def get_learning_profile(
    student_username: str,
    course_id: int | None = None,
    db: Session = Depends(get_db),
):
    student = _get_student_by_username(db, student_username)
    course_query = db.query(Course).filter(Course.status == "active")
    if course_id:
        course_query = course_query.filter(Course.id == course_id)
    courses = course_query.order_by(Course.created_at.desc()).all()
    rows, _ = _mastery_rows_for_student(db, student=student, courses=courses)
    course_cards, chapter_cards = _group_student_profile(rows)

    recommended = sorted(
        [row for row in rows if row["mastery_level"] < 0.8],
        key=lambda row: (-row["priority"], row["mastery_level"], row["practice_count"]),
    )[:6]
    weak_points = sorted(
        [row for row in rows if row["mastery_level"] < 0.6],
        key=lambda row: (-row["priority"], row["mastery_level"]),
    )[:8]
    recent_events = (
        db.query(KnowledgeMasteryEvent)
        .filter(KnowledgeMasteryEvent.student_id == student.id)
        .order_by(KnowledgeMasteryEvent.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "student": {
            "id": student.id,
            "username": student.user.username if student.user else student_username,
            "real_name": student.real_name,
            "student_no": student.student_no,
            "class_name": student.class_name,
            "grade_name": student.grade_name,
            "major": student.major,
        },
        "summary": _summarize_mastery_rows(rows),
        "courses": course_cards,
        "chapters": chapter_cards,
        "weak_points": weak_points,
        "recommended_practice": recommended,
        "recent_events": [
            {
                "id": event.id,
                "knowledge_point_id": event.knowledge_point_id,
                "knowledge_point_name": event.knowledge_point.name if event.knowledge_point else "",
                "course_name": event.knowledge_point.course.name
                if event.knowledge_point and event.knowledge_point.course
                else "",
                "source_type": event.source_type,
                "source_id": event.source_id,
                "score": event.score,
                "max_score": event.max_score,
                "is_correct": event.is_correct,
                "mastery_delta": event.mastery_delta,
                "created_at": event.created_at,
            }
            for event in recent_events
        ],
    }


@router.get("/teacher-dashboard")
async def get_teacher_learning_dashboard(
    teacher_username: str,
    course_id: int | None = None,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, teacher_username)
    all_teacher_courses = (
        db.query(Course)
        .filter(Course.teacher_id == teacher.id)
        .order_by(Course.created_at.desc())
        .all()
    )
    course_query = db.query(Course).filter(Course.teacher_id == teacher.id)
    if course_id:
        course_query = course_query.filter(Course.id == course_id)
    courses = course_query.order_by(Course.created_at.desc()).all()
    students = db.query(Student).order_by(Student.class_name.asc(), Student.real_name.asc()).all()

    student_profiles = []
    all_rows: list[dict] = []
    for student in students:
        rows, _ = _mastery_rows_for_student(db, student=student, courses=courses)
        summary = _summarize_mastery_rows(rows)
        all_rows.extend(rows)
        weak_points = sorted(
            [row for row in rows if row["mastery_level"] < 0.6],
            key=lambda row: (-row["priority"], row["mastery_level"]),
        )[:3]
        latest = max(
            [row["last_practiced_at"] for row in rows if row["last_practiced_at"]],
            default=None,
        )
        student_profiles.append(
            {
                "student": {
                    "id": student.id,
                    "username": student.user.username if student.user else None,
                    "real_name": student.real_name,
                    "student_no": student.student_no,
                    "class_name": student.class_name,
                    "grade_name": student.grade_name,
                    "major": student.major,
                },
                "summary": summary,
                "weak_points": weak_points,
                "last_practiced_at": latest,
            }
        )

    course_cards = []
    for course in courses:
        course_rows = [row for row in all_rows if row["course_id"] == course.id]
        course_cards.append(
            {
                "course": _course_payload(course),
                "summary": _summarize_mastery_rows(course_rows),
                "at_risk_students": [
                    profile
                    for profile in student_profiles
                    if profile["summary"]["knowledge_point_count"] > 0
                    and profile["summary"]["average_mastery"] < 0.4
                ][:5],
            }
        )

    student_profiles.sort(
        key=lambda profile: (
            profile["summary"]["average_mastery"],
            -profile["summary"]["weak_count"],
            profile["student"]["real_name"],
        )
    )
    return {
        "teacher": {
            "id": teacher.id,
            "username": teacher.user.username if teacher.user else teacher_username,
            "real_name": teacher.real_name,
            "department": teacher.department,
        },
        "courses": [_course_payload(course) for course in all_teacher_courses],
        "summary": {
            **_summarize_mastery_rows(all_rows),
            "student_count": len(students),
            "course_count": len(courses),
        },
        "course_cards": course_cards,
        "student_profiles": student_profiles,
    }


@router.post("")
async def create_course(request: CourseCreateRequest, db: Session = Depends(get_db)):
    teacher = _get_teacher_by_username(db, request.teacher_username)
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="课程名称不能为空")

    course = Course(
        teacher_id=teacher.id,
        name=name,
        description=request.description.strip(),
    )
    db.add(course)
    _commit_or_conflict(db, "该教师下已经存在同名课程")
    db.refresh(course)
    return {"success": True, "course": _course_payload(course)}


@router.get("/{course_id}")
async def get_course(course_id: int, db: Session = Depends(get_db)):
    course = _get_course(db, course_id)
    return {"course": _course_payload(course)}


@router.put("/{course_id}")
async def update_course(
    course_id: int,
    request: CourseUpdateRequest,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, request.teacher_username)
    course = _get_course(db, course_id)
    _ensure_teacher_owns_course(teacher, course)

    if request.name is not None:
        name = request.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="课程名称不能为空")
        course.name = name
    if request.description is not None:
        course.description = request.description.strip()
    if request.status is not None:
        course.status = request.status
    course.updated_at = datetime.utcnow()

    _commit_or_conflict(db, "该教师下已经存在同名课程")
    db.refresh(course)
    return {"success": True, "course": _course_payload(course)}


@router.delete("/{course_id}")
async def delete_course(
    course_id: int,
    teacher_username: str,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, teacher_username)
    course = _get_course(db, course_id)
    _ensure_teacher_owns_course(teacher, course)
    _delete_course_children(db, course.id)
    db.delete(course)
    db.commit()
    return {"success": True}


@router.get("/{course_id}/chapters")
async def list_chapters(course_id: int, db: Session = Depends(get_db)):
    _get_course(db, course_id)
    chapters = (
        db.query(CourseChapter)
        .filter(CourseChapter.course_id == course_id)
        .order_by(CourseChapter.order_index.asc())
        .all()
    )
    return {"chapters": [_chapter_payload(chapter) for chapter in chapters], "total": len(chapters)}


@router.post("/{course_id}/chapters")
async def create_chapter(
    course_id: int,
    request: ChapterCreateRequest,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, request.teacher_username)
    course = _get_course(db, course_id)
    _ensure_teacher_owns_course(teacher, course)

    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="章节标题不能为空")

    chapter = CourseChapter(
        course_id=course.id,
        title=title,
        description=request.description.strip(),
        order_index=request.order_index,
    )
    db.add(chapter)
    _commit_or_conflict(db, "该课程下已经存在同名或同顺序章节")
    db.refresh(chapter)
    return {"success": True, "chapter": _chapter_payload(chapter)}


@router.put("/chapters/{chapter_id}")
async def update_chapter(
    chapter_id: int,
    request: ChapterUpdateRequest,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, request.teacher_username)
    chapter = _get_chapter(db, chapter_id)
    _ensure_teacher_owns_course(teacher, chapter.course)

    if request.title is not None:
        title = request.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="章节标题不能为空")
        chapter.title = title
    if request.description is not None:
        chapter.description = request.description.strip()
    if request.order_index is not None:
        chapter.order_index = request.order_index
    chapter.updated_at = datetime.utcnow()

    _commit_or_conflict(db, "该课程下已经存在同名或同顺序章节")
    db.refresh(chapter)
    return {"success": True, "chapter": _chapter_payload(chapter)}


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(
    chapter_id: int,
    teacher_username: str,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, teacher_username)
    chapter = _get_chapter(db, chapter_id)
    _ensure_teacher_owns_course(teacher, chapter.course)
    _delete_chapter_children(db, chapter.id)
    db.delete(chapter)
    db.commit()
    return {"success": True}


@router.get("/{course_id}/materials")
async def list_materials(
    course_id: int,
    chapter_id: int | None = None,
    source_type: str | None = None,
    db: Session = Depends(get_db),
):
    _get_course(db, course_id)
    query = db.query(CourseMaterial).filter(CourseMaterial.course_id == course_id)
    if chapter_id is not None:
        query = query.filter(CourseMaterial.chapter_id == chapter_id)
    if source_type:
        query = query.filter(CourseMaterial.source_type == source_type)
    materials = query.order_by(CourseMaterial.created_at.desc()).all()
    return {"materials": [_material_payload(material) for material in materials], "total": len(materials)}


@router.post("/{course_id}/materials")
async def create_material_metadata(
    course_id: int,
    request: MaterialCreateRequest,
    db: Session = Depends(get_db),
):
    course = _get_course(db, course_id)
    uploader = _get_user_by_username(db, request.uploader_username)

    chapter = None
    scope: MaterialScope = "course_public"
    if request.chapter_id is not None:
        chapter = _get_course_chapter(db, course.id, request.chapter_id)
        scope = "chapter"
    elif request.source_type == "student_note":
        raise HTTPException(status_code=400, detail="学生笔记必须归属到具体章节")

    student_uploader_id = None
    if request.source_type == "student_note":
        student_uploader_id = _get_student_by_username(db, request.uploader_username).id
    else:
        teacher = _get_teacher_by_username(db, request.uploader_username)
        _ensure_teacher_owns_course(teacher, course)

    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="资料标题不能为空")

    material = CourseMaterial(
        course_id=course.id,
        chapter_id=chapter.id if chapter else None,
        uploader_user_id=uploader.id,
        student_uploader_id=student_uploader_id,
        title=title,
        description=request.description.strip(),
        source_type=request.source_type,
        original_filename=request.original_filename,
        file_path=request.file_path,
        file_type=request.file_type,
        kb_name=request.kb_name or _auto_kb_name(course.id, chapter.id if chapter else None, scope),
        rag_provider=request.rag_provider,
        parse_status=request.parse_status,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return {"success": True, "material": _material_payload(material)}


@router.post("/{course_id}/materials/upload")
async def upload_course_material(
    course_id: int,
    background_tasks: BackgroundTasks,
    uploader_username: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    source_type: Literal["teacher_material", "student_note"] = Form("teacher_material"),
    material_scope: MaterialScope = Form("chapter"),
    chapter_id: int | None = Form(None),
    rag_provider: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    course = _get_course(db, course_id)
    uploader = _get_user_by_username(db, uploader_username)

    if source_type == "student_note" and material_scope != "chapter":
        raise HTTPException(status_code=400, detail="学生笔记必须归属到具体章节")
    if material_scope == "chapter" and chapter_id is None:
        raise HTTPException(status_code=400, detail="章节资料必须选择章节")

    chapter = None
    if chapter_id is not None:
        chapter = _get_course_chapter(db, course.id, chapter_id)

    student_uploader_id = None
    if source_type == "student_note":
        student_uploader_id = _get_student_by_username(db, uploader_username).id
    else:
        teacher = _get_teacher_by_username(db, uploader_username)
        _ensure_teacher_owns_course(teacher, course)

    clean_title = title.strip() or (file.filename or "").strip()
    if not clean_title:
        raise HTTPException(status_code=400, detail="资料标题不能为空")

    provider = normalize_rag_provider(rag_provider)
    validate_rag_provider_files(provider, [file.filename or ""])
    allowed_extensions = set(get_provider_supported_extensions(provider)) & COURSE_MATERIAL_ALLOWED_EXTENSIONS
    if not allowed_extensions:
        allowed_extensions = set(get_provider_supported_extensions(provider))

    effective_scope: MaterialScope = "chapter" if chapter else "course_public"
    file_path, file_type, file_size = _save_course_material_file(
        file=file,
        course_id=course.id,
        chapter_id=chapter.id if chapter else None,
        source_type=source_type,
        scope=effective_scope,
        allowed_extensions=allowed_extensions,
    )

    kb_name = _auto_kb_name(course.id, chapter.id if chapter else None, effective_scope)
    material = CourseMaterial(
        course_id=course.id,
        chapter_id=chapter.id if chapter else None,
        uploader_user_id=uploader.id,
        student_uploader_id=student_uploader_id,
        title=clean_title,
        description=description.strip(),
        source_type=source_type,
        original_filename=file.filename,
        file_path=file_path,
        file_type=file_type,
        kb_name=kb_name,
        rag_provider=provider,
        parse_status="parsing",
    )
    db.add(material)
    db.commit()
    db.refresh(material)

    _enqueue_course_material_rag(
        background_tasks=background_tasks,
        material_id=material.id,
        kb_name=kb_name,
        file_path=file_path,
        rag_provider=provider,
        display_name=clean_title,
        course_id=course.id,
        chapter_id=chapter.id if chapter else None,
        source_type=source_type,
    )

    payload = _material_payload(material)
    payload["file_size"] = file_size
    return {"success": True, "material": payload}


@router.put("/materials/{material_id}")
async def update_material(
    material_id: int,
    request: MaterialUpdateRequest,
    db: Session = Depends(get_db),
):
    material = _get_material(db, material_id)
    _ensure_material_operator(db, request.operator_username, material)

    if request.title is not None:
        title = request.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="资料标题不能为空")
        material.title = title
    if request.description is not None:
        material.description = request.description.strip()
    if request.chapter_id is not None:
        chapter = _get_course_chapter(db, material.course_id, request.chapter_id)
        material.chapter_id = chapter.id
        material.kb_name = _auto_kb_name(material.course_id, chapter.id, "chapter")
    if request.parse_status is not None:
        material.parse_status = request.parse_status.strip()
    if request.rag_provider is not None:
        material.rag_provider = request.rag_provider.strip()
    material.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(material)
    return {"success": True, "material": _material_payload(material)}


@router.delete("/materials/{material_id}")
async def delete_material(
    material_id: int,
    operator_username: str,
    db: Session = Depends(get_db),
):
    material = _get_material(db, material_id)
    _ensure_material_operator(db, operator_username, material)
    db.delete(material)
    db.commit()
    return {"success": True}


@router.get("/{course_id}/knowledge-points")
async def list_knowledge_points(
    course_id: int,
    student_username: str | None = None,
    confirmed_only: bool = False,
    db: Session = Depends(get_db),
):
    _get_course(db, course_id)
    query = db.query(KnowledgePoint).filter(KnowledgePoint.course_id == course_id)
    if confirmed_only:
        query = query.filter(KnowledgePoint.is_confirmed.is_(True))
    points = query.order_by(KnowledgePoint.priority.desc(), KnowledgePoint.created_at.asc()).all()

    mastery_map: dict[int, StudentKnowledgeMastery] = {}
    if student_username and points:
        student = _get_student_by_username(db, student_username)
        records = (
            db.query(StudentKnowledgeMastery)
            .filter(
                StudentKnowledgeMastery.student_id == student.id,
                StudentKnowledgeMastery.knowledge_point_id.in_([point.id for point in points]),
            )
            .all()
        )
        mastery_map = {record.knowledge_point_id: record for record in records}

    return {
        "knowledge_points": [
            _knowledge_point_payload(point, mastery_map.get(point.id)) for point in points
        ],
        "total": len(points),
    }


@router.post("/{course_id}/knowledge-points")
async def create_knowledge_point(
    course_id: int,
    request: KnowledgePointCreateRequest,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, request.teacher_username)
    course = _get_course(db, course_id)
    _ensure_teacher_owns_course(teacher, course)

    if request.chapter_id:
        _get_course_chapter(db, course.id, request.chapter_id)

    if request.source_material_id:
        material_exists = (
            db.query(CourseMaterial)
            .filter(CourseMaterial.id == request.source_material_id, CourseMaterial.course_id == course.id)
            .first()
        )
        if not material_exists:
            raise HTTPException(status_code=404, detail="来源资料不存在或不属于该课程")

    point = KnowledgePoint(
        course_id=course.id,
        chapter_id=request.chapter_id,
        source_material_id=request.source_material_id,
        created_by_teacher_id=teacher.id,
        name=request.name.strip(),
        description=request.description.strip(),
        priority=request.priority,
        source_type=request.source_type,
        source_ref=request.source_ref,
        is_confirmed=request.is_confirmed,
    )
    db.add(point)
    _commit_or_conflict(db, "该章节下已经存在同名知识点")
    db.refresh(point)
    return {"success": True, "knowledge_point": _knowledge_point_payload(point)}


@router.put("/knowledge-points/{point_id}")
async def update_knowledge_point(
    point_id: int,
    request: KnowledgePointUpdateRequest,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, request.teacher_username)
    point = _get_knowledge_point(db, point_id)
    _ensure_teacher_owns_course(teacher, point.course)

    if request.name is not None:
        point.name = request.name.strip()
    if request.description is not None:
        point.description = request.description.strip()
    if request.priority is not None:
        point.priority = request.priority
    if request.is_confirmed is not None:
        point.is_confirmed = request.is_confirmed
    point.updated_at = datetime.utcnow()

    _commit_or_conflict(db, "该章节下已经存在同名知识点")
    db.refresh(point)
    return {"success": True, "knowledge_point": _knowledge_point_payload(point)}


@router.delete("/knowledge-points/{point_id}")
async def delete_knowledge_point(
    point_id: int,
    teacher_username: str,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, teacher_username)
    point = _get_knowledge_point(db, point_id)
    _ensure_teacher_owns_course(teacher, point.course)
    _delete_knowledge_points_with_records(db, [point.id])
    db.commit()
    return {"success": True}


@router.post("/knowledge-points/{point_id}/mastery-events")
async def create_mastery_event(
    point_id: int,
    request: MasteryEventCreateRequest,
    db: Session = Depends(get_db),
):
    student = _get_student_by_username(db, request.student_username)
    point = _get_knowledge_point(db, point_id)
    result = apply_mastery_event(
        db,
        student_id=student.id,
        knowledge_point_id=point.id,
        source_type=request.source_type,
        source_id=request.source_id,
        difficulty=request.difficulty,
        answer_quality=request.answer_quality,
        used_hint=request.used_hint,
        attempt_count=request.attempt_count,
        score=request.score,
        max_score=request.max_score,
        is_correct=request.is_correct,
        mastery_delta=request.mastery_delta,
        note=request.note,
    )
    db.commit()
    event = result.event
    mastery = result.mastery
    db.refresh(mastery)
    db.refresh(event)
    return {
        "success": True,
        "event": {
            "id": event.id,
            "source_type": event.source_type,
            "source_id": event.source_id,
            "score": event.score,
            "max_score": event.max_score,
            "is_correct": event.is_correct,
            "mastery_delta": event.mastery_delta,
            "note": event.note,
            "strategy": result.details,
            "created_at": event.created_at,
        },
        "knowledge_point": _knowledge_point_payload(point, mastery),
    }


@router.post("/knowledge-points/mastery-events/batch")
async def create_mastery_events_batch(
    request: MasteryEventBatchCreateRequest,
    db: Session = Depends(get_db),
):
    if not request.events:
        raise HTTPException(status_code=400, detail="events is required")
    student = _get_student_by_username(db, request.student_username)
    responses = []
    for item in request.events:
        point = _get_knowledge_point(db, item.knowledge_point_id)
        result = apply_mastery_event(
            db,
            student_id=student.id,
            knowledge_point_id=point.id,
            source_type=item.source_type,
            source_id=item.source_id,
            difficulty=item.difficulty,
            answer_quality=item.answer_quality,
            used_hint=item.used_hint,
            attempt_count=item.attempt_count,
            score=item.score,
            max_score=item.max_score,
            is_correct=item.is_correct,
            mastery_delta=item.mastery_delta,
            note=item.note,
        )
        responses.append(
            {
                "event_id": result.event.id,
                "strategy": result.details,
                "knowledge_point": _knowledge_point_payload(point, result.mastery),
            }
        )
    db.commit()
    return {"success": True, "events": responses}


@router.get("/{course_id}/mastery")
async def get_course_mastery(
    course_id: int,
    student_username: str,
    db: Session = Depends(get_db),
):
    _get_course(db, course_id)
    student = _get_student_by_username(db, student_username)
    point_ids = [
        point_id
        for (point_id,) in db.query(KnowledgePoint.id)
        .filter(KnowledgePoint.course_id == course_id)
        .all()
    ]
    if not point_ids:
        return {
            "summary": {
                "knowledge_point_count": 0,
                "mastered_count": 0,
                "weak_count": 0,
                "average_mastery": 0,
            },
            "records": [],
        }

    records = (
        db.query(StudentKnowledgeMastery)
        .filter(
            StudentKnowledgeMastery.student_id == student.id,
            StudentKnowledgeMastery.knowledge_point_id.in_(point_ids),
        )
        .all()
    )
    average = (
        sum(float(record.mastery_level or 0.0) for record in records) / len(point_ids)
        if point_ids
        else 0
    )
    return {
        "summary": {
            "knowledge_point_count": len(point_ids),
            "mastered_count": len([record for record in records if record.mastery_level >= 0.8]),
            "weak_count": len([record for record in records if record.mastery_level < 0.4]),
            "average_mastery": round(average, 4),
        },
        "records": [
            {
                "knowledge_point_id": record.knowledge_point_id,
                "mastery_level": record.mastery_level,
                "correct_count": record.correct_count,
                "wrong_count": record.wrong_count,
                "practice_count": record.practice_count,
                "last_practiced_at": record.last_practiced_at,
            }
            for record in records
        ],
    }
