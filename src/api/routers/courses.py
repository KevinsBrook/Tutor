from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import shutil
from typing import Literal
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from src.core.database import SessionLocal, get_db
from src.core.models import (
    Course,
    CourseChapter,
    CourseMaterial,
    KnowledgePointAlias,
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
    generate_node_explanation_cache,
    get_provider_supported_extensions,
    is_knowledge_base_initialized,
    normalize_rag_provider,
    run_initialization_task,
    run_upload_processing_task,
    validate_rag_provider_files,
    _safe_read_json,
)
from src.services.llm import complete as llm_complete
from src.services.mastery import apply_mastery_event

router = APIRouter()
logger = logging.getLogger(__name__)

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
    db.query(KnowledgePointAlias).filter(
        KnowledgePointAlias.knowledge_point_id.in_(point_ids),
    ).delete(synchronize_session=False)
    db.query(StudentKnowledgeMastery).filter(
        StudentKnowledgeMastery.knowledge_point_id.in_(point_ids),
    ).delete(synchronize_session=False)
    db.query(KnowledgeMasteryEvent).filter(
        KnowledgeMasteryEvent.knowledge_point_id.in_(point_ids),
    ).delete(synchronize_session=False)
    db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).delete(
        synchronize_session=False,
    )


def _delete_material_file(file_path: str | None) -> None:
    if not file_path:
        return
    try:
        target = Path(file_path).resolve()
        root = COURSE_MATERIAL_ROOT.resolve()
        if root not in target.parents and target != root:
            return
        if target.is_file():
            target.unlink()
    except Exception:
        return


def _delete_knowledge_base_storage(kb_name: str | None) -> None:
    if not kb_name:
        return
    try:
        get_kb_manager().delete_knowledge_base(kb_name, confirm=True)
    except ValueError:
        return
    except Exception:
        return


def _reset_stale_course_kb_if_unreferenced(db: Session, kb_name: str | None) -> None:
    """Drop a broken auto course KB before a fresh upload reuses the same KB name."""
    if not kb_name:
        return
    manager = get_kb_manager()
    if kb_name not in manager.list_knowledge_bases() or is_knowledge_base_initialized(kb_name):
        return
    references = db.query(CourseMaterial.id).filter(CourseMaterial.kb_name == kb_name).first()
    if references:
        return
    _delete_knowledge_base_storage(kb_name)


def _cleanup_material_files_and_kbs(materials: list[CourseMaterial]) -> None:
    kb_names = {material.kb_name for material in materials if material.kb_name}
    for material in materials:
        _delete_material_file(material.file_path)
    for kb_name in kb_names:
        _delete_knowledge_base_storage(kb_name)


def _delete_course_children(db: Session, course_id: int) -> None:
    materials = db.query(CourseMaterial).filter(CourseMaterial.course_id == course_id).all()
    point_ids = [
        point_id
        for (point_id,) in db.query(KnowledgePoint.id)
        .filter(KnowledgePoint.course_id == course_id)
        .all()
    ]
    _delete_knowledge_points_with_records(db, point_ids)
    _cleanup_material_files_and_kbs(materials)
    db.query(CourseMaterial).filter(CourseMaterial.course_id == course_id).delete(
        synchronize_session=False,
    )
    db.query(CourseChapter).filter(CourseChapter.course_id == course_id).delete(
        synchronize_session=False,
    )


def _delete_chapter_children(db: Session, chapter_id: int) -> None:
    materials = db.query(CourseMaterial).filter(CourseMaterial.chapter_id == chapter_id).all()
    point_ids = [
        point_id
        for (point_id,) in db.query(KnowledgePoint.id)
        .filter(KnowledgePoint.chapter_id == chapter_id)
        .all()
    ]
    _delete_knowledge_points_with_records(db, point_ids)
    _cleanup_material_files_and_kbs(materials)
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


def _safe_kb_name_from_filename(filename: str | None) -> str:
    stem = Path(filename or "").stem.strip()
    if not stem:
        stem = "course_material"
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem)
    stem = re.sub(r"\s+", "_", stem).strip("._ ")
    stem = stem[:120].strip("._ ")
    return stem or "course_material"


def _unique_course_material_kb_name(db: Session, filename: str | None) -> str:
    base = _safe_kb_name_from_filename(filename)
    existing = {
        name
        for (name,) in db.query(CourseMaterial.kb_name)
        .filter(CourseMaterial.kb_name.isnot(None))
        .all()
        if name
    }
    try:
        existing.update(get_kb_manager().list_knowledge_bases())
    except Exception:
        pass
    if base not in existing:
        return base
    for index in range(2, 1000):
        candidate = f"{base}_{index}"
        if candidate not in existing:
            return candidate
    return f"{base}_{uuid.uuid4().hex[:8]}"


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
            "group_type": "course",
            "subgroup_type": "chapter" if chapter_id else "course_public",
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
            "group_type": "course",
            "subgroup_type": "chapter" if chapter_id else "course_public",
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


def _compact_text(text: str, max_len: int = 360) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."


_EXPLANATION_NOISE_RE = re.compile(
    r"(<\s*/?\s*SEP\s*>|&lt;\s*/?\s*SEP\s*&gt;|<\|[^>]*\|>|##+|={3,}|-{4,})",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；;.!?])\s*|[\r\n]+")
_DEFINITION_RE = re.compile(
    r"(是|指|表示|定义为|称为|用于|用来|包括|包含|由.+组成|体现|描述|refers to|means|"
    r"is a|is an|is the|are the|defined as|used to|consists of|includes)",
    re.IGNORECASE,
)


def _sanitize_explanation_text(text: str, max_len: int = 700) -> str:
    raw = str(text or "")
    raw = raw.replace("\\n", " ").replace("\\t", " ")
    raw = raw.replace("\u0000", " ").replace("\ufeff", " ").replace("\u200b", " ")
    raw = _EXPLANATION_NOISE_RE.sub(" ", raw)
    raw = re.sub(r'["“”]{2,}', '"', raw)
    raw = re.sub(r"[|]{2,}", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" \t\r\n,，;；。")
    return _compact_text(raw, max_len)


def _normalize_for_match(text: str) -> str:
    return re.sub(r"[\s_`'\"“”‘’（）()【】\[\]{}<>《》:：,，.。;；、-]+", "", str(text or "").lower())


def _mentions_label(text: str, label: str) -> bool:
    normalized_text = _normalize_for_match(text)
    normalized_label = _normalize_for_match(label)
    if not normalized_text or not normalized_label:
        return False
    if normalized_label in normalized_text:
        return True

    ascii_terms = [
        part.lower()
        for part in re.split(r"[\s_\-/]+", str(label or ""))
        if len(part.strip()) >= 3 and part.isascii()
    ]
    return bool(ascii_terms) and all(term in str(text or "").lower() for term in ascii_terms)


def _split_explanation_sentences(text: str) -> list[str]:
    cleaned = _sanitize_explanation_text(text, 1200)
    if not cleaned:
        return []
    sentences = [
        _sanitize_explanation_text(sentence, 260)
        for sentence in _SENTENCE_SPLIT_RE.split(cleaned)
        if sentence and sentence.strip()
    ]
    if len(sentences) == 1 and len(sentences[0]) > 260:
        long_text = sentences[0]
        sentences = [long_text[i : i + 220] for i in range(0, min(len(long_text), 660), 220)]
    return [sentence for sentence in sentences if len(sentence) >= 8]


def _definition_signal(text: str) -> bool:
    return bool(_DEFINITION_RE.search(str(text or "")))


def _candidate_noise_penalty(original: str, cleaned: str) -> int:
    penalty = 0
    raw = str(original or "")
    if _EXPLANATION_NOISE_RE.search(raw):
        penalty += 35
    if len(cleaned) < 10:
        penalty += 25
    if len(cleaned) > 420:
        penalty += 10
    if cleaned.count("{") + cleaned.count("}") + cleaned.count("[") + cleaned.count("]") >= 4:
        penalty += 20
    if re.search(r"\b(chunk|entity_name|source_id|<sep>|vector|embedding)\b", cleaned, re.IGNORECASE):
        penalty += 15
    return penalty


def _score_supported_explanation(label: str, text: str, *, source: str) -> int:
    cleaned = _sanitize_explanation_text(text)
    score = 0
    if _mentions_label(cleaned, label):
        score += 28
    else:
        score -= 30
    if _definition_signal(cleaned):
        score += 22
    if 18 <= len(cleaned) <= 240:
        score += 18
    elif 10 <= len(cleaned) <= 360:
        score += 10
    if source in {"entity_chunk", "text_chunk"}:
        score += 18
    elif source == "vdb_entities":
        score += 14
    elif source == "graph_description":
        score += 8
    if "。" in cleaned or "." in cleaned or "；" in cleaned or ";" in cleaned:
        score += 5
    score -= _candidate_noise_penalty(text, cleaned)
    return max(0, min(100, score))


def _best_sentence_from_content(label: str, content: str, *, source: str) -> dict:
    sentences = _split_explanation_sentences(content)
    if not sentences:
        cleaned = _sanitize_explanation_text(content)
        return {
            "text": cleaned,
            "score": _score_supported_explanation(label, cleaned, source=source),
            "source": source,
        }

    best = {"text": "", "score": 0, "source": source}
    for index, sentence in enumerate(sentences):
        window = sentence
        if index + 1 < len(sentences) and len(window) < 140:
            next_sentence = sentences[index + 1]
            if _mentions_label(next_sentence, label) or _definition_signal(next_sentence):
                window = f"{window}{next_sentence}"
        score = _score_supported_explanation(label, window, source=source)
        if score > best["score"]:
            best = {"text": _sanitize_explanation_text(window, 320), "score": score, "source": source}
    return best


def _dict_get_case_insensitive(data: dict, key: str):
    if key in data:
        return data[key]
    lowered = key.lower()
    for item_key, value in data.items():
        if str(item_key).lower() == lowered:
            return value
    return None


_ENGLISH_TO_CHINESE_KP_ALIASES = {
    "accuracy": "准确率",
    "activation function": "激活函数",
    "adam": "Adam优化器",
    "attention mechanism": "注意力机制",
    "backpropagation": "反向传播",
    "bayes theorem": "贝叶斯定理",
    "bayes formula": "贝叶斯公式",
    "batch normalization": "批量归一化",
    "binary classification": "二分类",
    "classification": "分类",
    "clustering": "聚类",
    "conditional probability": "条件概率",
    "confusion matrix": "混淆矩阵",
    "convolution": "卷积",
    "convolutional neural network": "卷积神经网络",
    "cnn": "卷积神经网络",
    "cross entropy": "交叉熵",
    "decision tree": "决策树",
    "deep learning": "深度学习",
    "dropout": "Dropout",
    "embedding": "嵌入",
    "epoch": "训练轮次",
    "f1 score": "F1分数",
    "gradient descent": "梯度下降",
    "k means": "K均值",
    "linear regression": "线性回归",
    "logistic regression": "逻辑回归",
    "loss function": "损失函数",
    "machine learning": "机器学习",
    "mean squared error": "均方误差",
    "mse": "均方误差",
    "neural network": "神经网络",
    "overfitting": "过拟合",
    "precision": "精确率",
    "recall": "召回率",
    "relu": "ReLU",
    "regularization": "正则化",
    "reinforcement learning": "强化学习",
    "rnn": "循环神经网络",
    "recurrent neural network": "循环神经网络",
    "softmax": "Softmax",
    "supervised learning": "监督学习",
    "support vector machine": "支持向量机",
    "svm": "支持向量机",
    "transformer": "Transformer",
    "underfitting": "欠拟合",
    "unsupervised learning": "无监督学习",
}
_CHINESE_TO_ENGLISH_KP_ALIASES = {
    chinese: english for english, chinese in _ENGLISH_TO_CHINESE_KP_ALIASES.items()
}
_ENGLISH_TO_CHINESE_KP_ALIASES.update(
    {
        "ip address": "IP地址",
        "mac address": "MAC地址",
        "subnet mask": "子网掩码",
        "default gateway": "默认网关",
        "network layer": "网络层",
        "data link layer": "数据链路层",
        "transport layer": "传输层",
        "application layer": "应用层",
        "osi model": "OSI模型",
        "tcp protocol": "TCP协议",
        "udp protocol": "UDP协议",
        "ip protocol": "IP协议",
        "arp protocol": "ARP协议",
        "icmp protocol": "ICMP协议",
        "dhcp protocol": "DHCP协议",
        "dns protocol": "DNS协议",
        "http protocol": "HTTP协议",
        "https protocol": "HTTPS协议",
    }
)
_CHINESE_TO_ENGLISH_KP_ALIASES.update(
    {chinese: english for english, chinese in _ENGLISH_TO_CHINESE_KP_ALIASES.items()}
)
_CHINESE_SUFFIX_TO_ENGLISH_KP = {
    "地址": "address",
    "协议": "protocol",
    "模型": "model",
    "层": "layer",
    "网关": "gateway",
    "掩码": "mask",
    "子网": "subnet",
    "端口": "port",
    "路由器": "router",
    "交换机": "switch",
}


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _normalize_alias_key(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())


def _english_alias_key(text: str) -> str:
    normalized = re.sub(r"[^0-9a-z]+", " ", str(text or "").lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def _mixed_cjk_english_alias_keys(text: str) -> set[str]:
    keys: set[str] = set()
    raw = str(text or "").strip()
    for ascii_part, cjk_part in re.findall(r"([A-Za-z][A-Za-z0-9+.-]*)\s*([\u4e00-\u9fff]{1,8})", raw):
        prefix = ascii_part.lower()
        suffix = _CHINESE_SUFFIX_TO_ENGLISH_KP.get(cjk_part)
        if suffix:
            keys.add(f"{prefix} {suffix}")
            keys.add(f"{prefix}{suffix}")
    return keys


def _extract_label_parts(label: str) -> list[str]:
    text = str(label or "").strip()
    if not text:
        return []
    parts = [text]
    parts.extend(
        match.strip()
        for match in re.findall(r"[\(（\[]([^()（）\[\]]+)[\)）\]]", text)
        if match.strip()
    )
    parts.extend(part.strip() for part in re.split(r"[/／|,，;；]", text) if part.strip())
    return list(dict.fromkeys(parts))


def _extract_chinese_label(label: str) -> str:
    text = str(label or "").strip()
    if not text or not _contains_cjk(text):
        return ""
    without_parentheses = re.sub(r"[\(（\[].*?[\)）\]]", " ", text)
    chunks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9·+\-]+", without_parentheses)
    chinese_chunks = [chunk.strip(" -+") for chunk in chunks if _contains_cjk(chunk)]
    if chinese_chunks:
        return max(chinese_chunks, key=len)
    return text


def _preferred_knowledge_point_name(label: str) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    chinese = _extract_chinese_label(text)
    if chinese:
        return chinese
    for part in _extract_label_parts(text):
        alias = _ENGLISH_TO_CHINESE_KP_ALIASES.get(_english_alias_key(part))
        if alias:
            return alias
    return text


def _knowledge_point_alias_keys(label: str) -> set[str]:
    keys: set[str] = set()
    original_key = _normalize_alias_key(label)
    if original_key:
        keys.add(original_key)
    for part in _extract_label_parts(label):
        normalized = _normalize_alias_key(part)
        if normalized:
            keys.add(normalized)
        english_key = _english_alias_key(part)
        if english_key:
            keys.add(english_key)
            keys.add(english_key.replace(" ", ""))
            chinese_alias = _ENGLISH_TO_CHINESE_KP_ALIASES.get(english_key)
            if chinese_alias:
                keys.add(_normalize_alias_key(chinese_alias))
        chinese = _extract_chinese_label(part)
        if chinese:
            keys.add(_normalize_alias_key(chinese))
            english_alias = _CHINESE_TO_ENGLISH_KP_ALIASES.get(chinese)
            if english_alias:
                keys.add(english_alias)
                keys.add(english_alias.replace(" ", ""))
        for mixed_key in _mixed_cjk_english_alias_keys(part):
            keys.add(mixed_key)
            keys.add(mixed_key.replace(" ", ""))
            chinese_alias = _ENGLISH_TO_CHINESE_KP_ALIASES.get(mixed_key)
            if chinese_alias:
                keys.add(_normalize_alias_key(chinese_alias))
    preferred = _preferred_knowledge_point_name(label)
    if preferred and preferred != label:
        keys.add(_normalize_alias_key(preferred))
    return {key for key in keys if key}


def _find_knowledge_point_by_alias(
    db: Session,
    course_id: int,
    chapter_id: int | None,
    name: str,
    exclude_id: int | None = None,
) -> KnowledgePoint | None:
    keys = _knowledge_point_alias_keys(name)
    keys.add(_normalize_alias_key(name))
    query = db.query(KnowledgePoint).filter(
        KnowledgePoint.course_id == course_id,
        KnowledgePoint.chapter_id == chapter_id,
    )
    if exclude_id is not None:
        query = query.filter(KnowledgePoint.id != exclude_id)

    alias_match = (
        db.query(KnowledgePointAlias)
        .filter(
            KnowledgePointAlias.course_id == course_id,
            KnowledgePointAlias.chapter_id == chapter_id,
            KnowledgePointAlias.alias_name == name,
        )
        .first()
    )
    if alias_match and (exclude_id is None or alias_match.knowledge_point_id != exclude_id):
        point = (
            db.query(KnowledgePoint)
            .filter(KnowledgePoint.id == alias_match.knowledge_point_id)
            .first()
        )
        if point:
            return point

    for point in query.all():
        point_keys = _knowledge_point_alias_keys(point.name)
        point_keys.add(_normalize_alias_key(point.name))
        if keys & point_keys:
            return point
    return None


def _detect_alias_language(alias_name: str) -> str:
    if _contains_cjk(alias_name):
        return "zh"
    if re.search(r"[A-Za-z]", alias_name):
        return "en"
    return "unknown"


def _record_knowledge_point_alias(
    db: Session,
    point: KnowledgePoint,
    alias_name: str,
    *,
    source: str,
    confidence: float,
    reason: str = "",
) -> None:
    alias = str(alias_name or "").strip()
    if not alias or alias == point.name:
        return
    for pending in db.new:
        if not isinstance(pending, KnowledgePointAlias):
            continue
        if (
            pending.course_id == point.course_id
            and pending.chapter_id == point.chapter_id
            and pending.alias_name == alias
        ):
            if pending.knowledge_point_id == point.id and confidence > float(pending.confidence or 0.0):
                pending.confidence = confidence
                pending.source = source
                pending.reason = reason[:1000]
            return
    existing = (
        db.query(KnowledgePointAlias)
        .filter(
            KnowledgePointAlias.course_id == point.course_id,
            KnowledgePointAlias.chapter_id == point.chapter_id,
            KnowledgePointAlias.alias_name == alias,
        )
        .first()
    )
    if existing:
        if existing.knowledge_point_id == point.id and confidence > float(existing.confidence or 0.0):
            existing.confidence = confidence
            existing.source = source
            existing.reason = reason[:1000]
        return
    db.add(
        KnowledgePointAlias(
            knowledge_point_id=point.id,
            course_id=point.course_id,
            chapter_id=point.chapter_id,
            alias_name=alias,
            alias_language=_detect_alias_language(alias),
            confidence=max(0.0, min(1.0, confidence)),
            source=source,
            reason=reason[:1000],
        )
    )


def _safe_json_object(text: str) -> dict:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        match = re.search(r"\{[\s\S]*\}", str(text or ""))
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}


async def _llm_judge_knowledge_point_duplicate(
    candidate_name: str,
    candidate_description: str,
    existing: KnowledgePoint,
) -> dict:
    system_prompt = (
        "你是课程知识点去重助手。判断两个术语是否指向同一个教学知识点，"
        "只输出 JSON，不要输出解释性正文。"
    )
    user_prompt = f"""
请判断候选知识点 A 与已有知识点 B 是否重复或中英文同义。

A 名称：{candidate_name}
A 描述：{candidate_description or "无"}

B 名称：{existing.name}
B 描述：{existing.description or "无"}

判定标准：
- 如果只是中英文表达、缩写/全称、大小写/空格差异，算重复。
- 如果一个是另一个的上位概念、相关概念、章节名、实体名，不算重复。
- canonical_name 优先使用中文教学术语；没有中文时用更简洁准确的名称。

返回 JSON：
{{
  "duplicate": true/false,
  "confidence": 0.0-1.0,
  "canonical_name": "保留名称",
  "alias_name": "被合并的别名",
  "reason": "一句话理由"
}}
"""
    try:
        response = await asyncio.wait_for(
            llm_complete(
                user_prompt,
                system_prompt=system_prompt,
                response_format={"type": "json_object"},
                temperature=0,
                max_retries=0,
            ),
            timeout=12,
        )
    except Exception:
        return {"duplicate": False, "confidence": 0.0, "reason": "llm_unavailable"}
    parsed = _safe_json_object(response)
    return {
        "duplicate": bool(parsed.get("duplicate")),
        "confidence": float(parsed.get("confidence") or 0.0),
        "canonical_name": str(parsed.get("canonical_name") or "").strip(),
        "alias_name": str(parsed.get("alias_name") or "").strip(),
        "reason": str(parsed.get("reason") or "").strip(),
    }


async def _find_duplicate_point_with_ai(
    db: Session,
    candidate_name: str,
    candidate_description: str,
    existing_records: list[KnowledgePoint],
) -> tuple[KnowledgePoint | None, dict | None]:
    for existing in existing_records[:30]:
        verdict = await _llm_judge_knowledge_point_duplicate(
            candidate_name,
            candidate_description,
            existing,
        )
        if verdict.get("reason") == "llm_unavailable":
            return None, None
        if verdict.get("duplicate") and float(verdict.get("confidence") or 0.0) >= 0.72:
            return existing, verdict
    return None, None


def _point_preference_score(point: KnowledgePoint) -> tuple[int, int, int, int]:
    return (
        1 if point.is_confirmed else 0,
        1 if _contains_cjk(point.name) else 0,
        int(point.priority or 0),
        len(str(point.description or "")),
    )


def _dedupe_knowledge_points(points: list[KnowledgePoint]) -> list[KnowledgePoint]:
    winners: list[KnowledgePoint] = []
    winner_by_key: dict[str, KnowledgePoint] = {}
    winner_index_by_id: dict[int, int] = {}

    for point in points:
        keys = _knowledge_point_alias_keys(point.name)
        keys.add(_normalize_alias_key(point.name))
        for alias in point.aliases or []:
            keys.update(_knowledge_point_alias_keys(alias.alias_name))
            keys.add(_normalize_alias_key(alias.alias_name))
        keys = {key for key in keys if key}
        existing = next((winner_by_key[key] for key in keys if key in winner_by_key), None)
        if existing is None:
            winner_index_by_id[point.id] = len(winners)
            winners.append(point)
            for key in keys:
                winner_by_key[key] = point
            continue

        if _point_preference_score(point) > _point_preference_score(existing):
            index = winner_index_by_id.get(existing.id)
            if index is not None:
                winners[index] = point
            winner_index_by_id.pop(existing.id, None)
            winner_index_by_id[point.id] = index if index is not None else len(winners)
            existing_keys = _knowledge_point_alias_keys(existing.name) | {_normalize_alias_key(existing.name)}
            for alias in existing.aliases or []:
                existing_keys.update(_knowledge_point_alias_keys(alias.alias_name))
                existing_keys.add(_normalize_alias_key(alias.alias_name))
            for key in existing_keys | keys:
                if key:
                    winner_by_key[key] = point

    return winners


def _lookup_cached_node_explanation(kb_dir: Path, node: dict, label: str) -> dict:
    cache_file = kb_dir / "rag_storage" / "node_explanations.json"
    if not cache_file.exists():
        return {"description": "", "confidence": 0, "method": "cache_missing"}
    try:
        cache = _safe_read_json(cache_file)
        if not isinstance(cache, dict):
            return {"description": "", "confidence": 0, "method": "cache_invalid"}
        nodes = cache.get("nodes")
        if not isinstance(nodes, dict):
            return {"description": "", "confidence": 0, "method": "cache_invalid"}
        node_id = str(node.get("id") or label).strip()
        record = nodes.get(node_id)
        if not isinstance(record, dict) and label != node_id:
            for item in nodes.values():
                if not isinstance(item, dict):
                    continue
                if str(item.get("label") or "").strip().lower() == label.lower():
                    record = item
                    break
        if not isinstance(record, dict):
            return {"description": "", "confidence": 0, "method": "cache_missing"}
        explanation = _sanitize_explanation_text(str(record.get("explanation") or ""), 900)
        if not explanation:
            return {"description": "", "confidence": 0, "method": "cache_empty"}
        cache_confidence = int(record.get("confidence") or 0)
        local_score = _score_supported_explanation(
            label,
            explanation,
            source="entity_chunk" if cache_confidence >= 60 else "graph_description",
        )
        return {
            "description": explanation,
            "confidence": max(cache_confidence, local_score),
            "method": f"cached_{record.get('explanation_source') or 'node_explanation'}",
        }
    except Exception:
        return {"description": "", "confidence": 0, "method": "cache_error"}


def _collect_graph_node_explanation_candidates(kb_dir: Path, node: dict, label: str) -> list[dict]:
    """Collect local evidence for a node without trusting any single store blindly."""
    candidates: list[dict] = []
    raw_description = str(node.get("description") or "").strip()
    if raw_description:
        candidates.append({"source": "graph_description", "content": raw_description})

    canonical_id = str(node.get("id") or label).strip()
    rag_storage_dir = kb_dir / "rag_storage"
    vdb_entities_file = rag_storage_dir / "vdb_entities.json"
    entity_chunks_file = rag_storage_dir / "kv_store_entity_chunks.json"
    text_chunks_file = rag_storage_dir / "kv_store_text_chunks.json"

    if vdb_entities_file.exists():
        try:
            vdb_data = _safe_read_json(vdb_entities_file)
            entity_records = vdb_data.get("data") if isinstance(vdb_data, dict) else None
            if isinstance(entity_records, list):
                best_content = ""
                for item in entity_records:
                    if not isinstance(item, dict):
                        continue
                    entity_name = str(item.get("entity_name") or "").strip()
                    if entity_name.lower() in {canonical_id.lower(), label.lower()}:
                        content = str(item.get("content") or "")
                        if len(content) > len(best_content):
                            best_content = content
                if best_content:
                    candidates.append({"source": "vdb_entities", "content": best_content})
        except Exception:
            pass

    chunk_ids: list[str] = []
    if entity_chunks_file.exists():
        try:
            entity_chunk_data = _safe_read_json(entity_chunks_file)
            if isinstance(entity_chunk_data, dict):
                rec = _dict_get_case_insensitive(entity_chunk_data, canonical_id)
                if rec is None and label != canonical_id:
                    rec = _dict_get_case_insensitive(entity_chunk_data, label)
                if isinstance(rec, dict):
                    raw_chunk_ids = rec.get("chunk_ids")
                    if isinstance(raw_chunk_ids, list):
                        chunk_ids = [str(cid) for cid in raw_chunk_ids if str(cid).strip()]
        except Exception:
            pass

    if chunk_ids and text_chunks_file.exists():
        try:
            text_chunks_data = _safe_read_json(text_chunks_file)
            if isinstance(text_chunks_data, dict):
                for cid in chunk_ids[:4]:
                    chunk_payload = text_chunks_data.get(cid)
                    if not isinstance(chunk_payload, dict):
                        continue
                    content = _compact_text(str(chunk_payload.get("content") or ""), 280)
                    if content:
                        candidates.append({"source": "entity_chunk", "content": content})
        except Exception:
            pass

    return candidates


def _lookup_graph_node_explanation(kb_dir: Path, node: dict, label: str) -> dict:
    cached = _lookup_cached_node_explanation(kb_dir, node, label)
    if cached["description"] and cached["confidence"] >= 60:
        return cached

    candidates = _collect_graph_node_explanation_candidates(kb_dir, node, label)
    best = {"text": "", "score": 0, "source": "none"}
    for candidate in candidates:
        content = str(candidate.get("content") or "")
        source = str(candidate.get("source") or "unknown")
        scored = _best_sentence_from_content(label, content, source=source)
        if scored["score"] > best["score"]:
            best = scored
    return {
        "description": best["text"],
        "confidence": best["score"],
        "method": best["source"],
    }


def _derive_knowledge_point_description(
    kb_dir: Path,
    node: dict,
    label: str,
    connected_labels: list[str],
    material: CourseMaterial,
    display_label: str | None = None,
) -> str:
    explicit = _lookup_graph_node_explanation(kb_dir, node, label)
    if explicit["description"] and explicit["confidence"] >= 60:
        return explicit["description"]
    source = material.title or material.original_filename or "课程资料"
    shown_label = display_label or label
    if connected_labels:
        related = "、".join(connected_labels[:4])
        suffix = "等概念" if len(connected_labels) > 4 else "等概念"
        return f"资料中暂未抽取到“{shown_label}”的稳定定义。系统仅识别到它与{related}{suffix}存在关联，建议教师确认时补充其定义、适用边界和典型例子。"
    return f"资料《{source}》中暂未抽取到“{shown_label}”的稳定定义。建议教师确认时补充其定义、适用边界和典型例子。"


def _derive_knowledge_point_explanation(
    kb_dir: Path,
    node: dict,
    label: str,
    connected_labels: list[str],
    material: CourseMaterial,
    display_label: str | None = None,
) -> dict:
    explicit = _lookup_graph_node_explanation(kb_dir, node, label)
    if explicit["description"] and explicit["confidence"] >= 60:
        return explicit
    return {
        "description": _derive_knowledge_point_description(
            kb_dir,
            node,
            label,
            connected_labels,
            material,
            display_label,
        ),
        "confidence": explicit["confidence"],
        "method": "needs_teacher_review",
    }


def _priority_from_graph_rank(rank: int, total: int, degree: int) -> int:
    if degree <= 0:
        return 1
    ratio = rank / max(1, total)
    if ratio <= 0.12 and degree >= 3:
        return 5
    if ratio <= 0.35 and degree >= 2:
        return 4
    if ratio <= 0.75:
        return 3
    return 2


_TEACHING_POINT_SUFFIX_RE = re.compile(
    r"(地址|协议|模型|算法|方法|机制|结构|公式|定理|概念|网络|路由|交换|"
    r"掩码|网关|端口|报文|数据报|分组|数据包|帧|层|表|队列|函数|矩阵|"
    r"分类|回归|聚类|损失|优化|梯度|概率|分布|编码|调制)$"
)
_CJK_TERM_RE = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9+.#/-]{0,12}\s*)?[\u4e00-\u9fff]{2,14}"
)
_ENGLISH_TERM_RE = re.compile(
    r"\b(?:[A-Z]{2,}|[A-Z][a-z]+)(?:[-\s]+(?:[A-Z]{2,}|[A-Z][a-z]+|[a-z]+)){0,4}\b"
)
_TERM_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "chapter",
    "figure",
    "table",
    "pdf",
    "xmu",
    "edu",
    "tanglu",
}
_CJK_PHRASE_START_NOISE_RE = re.compile(
    r"^(是|以|如果|每个|每一个|这就|为了|通过|包括|到|和|或|对|在|由|将|把|当|从|出|会|其|与)"
)


def _candidate_key(name: str) -> str:
    keys = _knowledge_point_alias_keys(name)
    if keys:
        return sorted(keys, key=len)[0]
    return _normalize_alias_key(name)


def _is_text_term_candidate(term: str) -> bool:
    text = str(term or "").strip(" \t\r\n,.;:!?()[]{}<>\"'")
    if len(text) < 2 or len(text) > 60:
        return False
    if _KNOWLEDGE_POINT_NOISE_RE.search(text):
        return False
    if re.fullmatch(r"[\d\s.,;:!?()\[\]{}<>+\-*/=_%|&]+", text):
        return False
    if text.lower() in _TERM_STOPWORDS:
        return False
    if re.search(r"[\u4e00-\u9fff]", text) and _CJK_PHRASE_START_NOISE_RE.search(text):
        return False
    if len(text) <= 2 and text in {"地址", "网络", "协议", "分组", "报文", "路由", "节点", "结点"}:
        return False
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_count = len(re.findall(r"[A-Za-z]", text))
    english_key = _english_alias_key(text)
    known_alias = (
        english_key in _ENGLISH_TO_CHINESE_KP_ALIASES
        or _extract_chinese_label(text) in _CHINESE_TO_ENGLISH_KP_ALIASES
    )
    if known_alias or _mixed_cjk_english_alias_keys(text):
        return True
    if cjk_count >= 2 and _TEACHING_POINT_SUFFIX_RE.search(text):
        return True
    if ascii_count >= 3 and len(text.split()) <= 5 and not text.islower():
        return True
    return False


def _extract_term_candidates_from_text(text: str, max_terms: int = 24) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for pattern in (_CJK_TERM_RE, _ENGLISH_TERM_RE):
        for match in pattern.finditer(str(text or "")):
            term = match.group(0).strip()
            if not _is_text_term_candidate(term):
                continue
            key = _candidate_key(term)
            if not key or key in seen:
                continue
            seen.add(key)
            terms.append(term)
            if len(terms) >= max_terms:
                return terms
    return terms


def _merge_teaching_candidate(
    candidates_by_key: dict[str, dict],
    *,
    name: str,
    source: str,
    evidence: str,
    priority_hint: int = 2,
    degree: int = 0,
    node: dict | None = None,
    related: list[str] | None = None,
    aliases: list[str] | None = None,
) -> None:
    display_name = _preferred_knowledge_point_name(name)
    if not display_name:
        return
    key = _candidate_key(display_name)
    if not key:
        return
    compact_evidence = _sanitize_explanation_text(evidence, 360)
    existing = candidates_by_key.get(key)
    if existing is None:
        candidates_by_key[key] = {
            "name": display_name,
            "raw_names": [name],
            "sources": [source],
            "evidence": [compact_evidence] if compact_evidence else [],
            "priority_hint": priority_hint,
            "degree": degree,
            "node": node or {},
            "related": related or [],
            "aliases": aliases or [],
        }
        return
    if name not in existing["raw_names"]:
        existing["raw_names"].append(name)
    if source not in existing["sources"]:
        existing["sources"].append(source)
    if compact_evidence and compact_evidence not in existing["evidence"]:
        existing["evidence"].append(compact_evidence)
    existing["priority_hint"] = max(int(existing.get("priority_hint") or 0), priority_hint)
    existing["degree"] = max(int(existing.get("degree") or 0), degree)
    existing["related"] = list(dict.fromkeys([*(existing.get("related") or []), *(related or [])]))[:8]
    existing["aliases"] = list(dict.fromkeys([*(existing.get("aliases") or []), *(aliases or [])]))[:12]
    if node and not existing.get("node"):
        existing["node"] = node


def _collect_text_store_candidates(
    kb_dir: Path,
    candidates_by_key: dict[str, dict],
    *,
    max_chunks: int = 80,
) -> None:
    text_chunks_file = kb_dir / "rag_storage" / "kv_store_text_chunks.json"
    if not text_chunks_file.exists():
        return
    try:
        data = _safe_read_json(text_chunks_file)
    except Exception:
        return
    records = data.values() if isinstance(data, dict) else data if isinstance(data, list) else []
    for index, item in enumerate(records):
        if index >= max_chunks:
            break
        if isinstance(item, dict):
            content = str(item.get("content") or item.get("text") or "")
        else:
            content = str(item or "")
        if not content.strip():
            continue
        for term in _extract_term_candidates_from_text(content):
            _merge_teaching_candidate(
                candidates_by_key,
                name=term,
                source="text_chunk",
                evidence=_best_sentence_from_content(term, content, source="text_chunk")["text"],
                priority_hint=3,
            )


def _iter_content_list_texts(kb_dir: Path):
    content_dir = kb_dir / "content_list"
    if not content_dir.exists():
        return
    for path in content_dir.glob("*.json"):
        try:
            data = _safe_read_json(path)
        except Exception:
            continue
        items = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict):
                parts = [
                    str(item.get(field) or "")
                    for field in ("title", "text", "content", "caption", "md_content")
                ]
                text = " ".join(part for part in parts if part)
            else:
                text = str(item or "")
            if text.strip():
                yield text


def _collect_content_list_candidates(kb_dir: Path, candidates_by_key: dict[str, dict]) -> None:
    for index, content in enumerate(_iter_content_list_texts(kb_dir) or []):
        if index >= 120:
            break
        for term in _extract_term_candidates_from_text(content, max_terms=12):
            _merge_teaching_candidate(
                candidates_by_key,
                name=term,
                source="content_list",
                evidence=_best_sentence_from_content(term, content, source="text_chunk")["text"],
                priority_hint=3,
            )


def _collect_numbered_item_candidates(kb_dir: Path, candidates_by_key: dict[str, dict]) -> None:
    path = kb_dir / "numbered_items.json"
    if not path.exists():
        return
    try:
        data = _safe_read_json(path)
    except Exception:
        return
    items = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
    for item in items[:160]:
        if isinstance(item, dict):
            content = " ".join(
                str(item.get(field) or "") for field in ("title", "text", "content", "label")
            )
        else:
            content = str(item or "")
        for term in _extract_term_candidates_from_text(content, max_terms=8):
            _merge_teaching_candidate(
                candidates_by_key,
                name=term,
                source="numbered_item",
                evidence=_best_sentence_from_content(term, content, source="text_chunk")["text"],
                priority_hint=2,
            )


def _collect_graph_teaching_candidates(
    kb_dir: Path,
    nodes: list[dict],
    relation_labels: dict[str, list[str]],
    material: CourseMaterial,
    candidates_by_key: dict[str, dict],
    *,
    limit: int,
) -> None:
    for rank, node in enumerate(nodes[: limit * 3], start=1):
        label = str(node.get("label") or node.get("id") or "").strip()
        if not label or len(label) > 80:
            continue
        display_name = _preferred_knowledge_point_name(label)
        degree = int(node.get("degree") or 0)
        if not _is_probably_knowledge_point_label(display_name or label, node, degree):
            continue
        related = relation_labels.get(str(node.get("id") or ""), [])
        explanation = _derive_knowledge_point_explanation(
            kb_dir,
            node,
            label,
            related,
            material,
            display_name,
        )
        _merge_teaching_candidate(
            candidates_by_key,
            name=display_name,
            source="graph",
            evidence=explanation["description"],
            priority_hint=_priority_from_graph_rank(rank, min(len(nodes), limit), degree),
            degree=degree,
            node=node,
            related=related,
            aliases=[str(alias) for alias in node.get("aliases", []) or []],
        )


async def _llm_filter_teaching_knowledge_points(
    candidates: list[dict],
    material: CourseMaterial,
    *,
    limit: int,
    use_llm: bool = True,
) -> list[dict]:
    if not candidates:
        return []
    approved: list[dict] = []
    material_name = material.title or material.original_filename or material.kb_name or ""
    llm_failed = False
    for start in range(0, len(candidates), 12):
        batch = candidates[start : start + 12]
        payload = [
            {
                "name": item["name"],
                "sources": item.get("sources", []),
                "evidence": item.get("evidence", [])[:2],
                "related": item.get("related", [])[:5],
            }
            for item in batch
        ]
        system_prompt = (
            "你是课程知识点抽取助手。只保留适合作为教学、练习、测评目标的核心概念、"
            "方法、规则、模型、协议或公式。排除文件名、章节标题、图表名、普通名词、"
            "例题碎片、过细实体、孤立英文缩写和无法讲授的短语。只输出 JSON。"
        )
        user_prompt = f"""
资料：{material_name}

候选项如下：
{json.dumps(payload, ensure_ascii=False)}

请输出：
{{
  "items": [
    {{
      "candidate_name": "原候选名称",
      "is_knowledge_point": true,
      "name": "规范知识点名称，优先中文或中英混合常用名",
      "aliases": ["同义名称"],
      "description": "一句适合学生理解的定义或说明",
      "priority": 1-5,
      "reason": "保留或剔除原因"
    }}
  ]
}}
"""
        if not use_llm or llm_failed:
            items = None
        else:
            try:
                response = await asyncio.wait_for(
                    llm_complete(
                        user_prompt,
                        system_prompt=system_prompt,
                        response_format={"type": "json_object"},
                        temperature=0,
                        max_retries=0,
                    ),
                    timeout=18,
                )
                parsed = _safe_json_object(response)
                items = parsed.get("items") if isinstance(parsed, dict) else None
            except Exception:
                llm_failed = True
                items = None
        if not isinstance(items, list):
            for item in batch:
                if "graph" not in (item.get("sources") or []) and int(item.get("priority_hint") or 0) < 4:
                    continue
                if len(approved) >= limit:
                    break
                approved.append(
                    {
                        **item,
                        "llm_name": item["name"],
                        "llm_aliases": item.get("aliases", []),
                        "llm_description": (item.get("evidence") or [""])[0],
                        "llm_priority": item.get("priority_hint") or 2,
                        "llm_reason": "LLM unavailable; kept by local evidence filter",
                        "llm_unavailable": True,
                    }
                )
            continue
        batch_by_name = {_normalize_alias_key(item["name"]): item for item in batch}
        for verdict in items:
            if not isinstance(verdict, dict) or not verdict.get("is_knowledge_point"):
                continue
            original_name = str(verdict.get("candidate_name") or verdict.get("name") or "").strip()
            source_item = batch_by_name.get(_normalize_alias_key(original_name))
            if source_item is None:
                source_item = next(
                    (
                        item
                        for item in batch
                        if _candidate_key(item["name"]) == _candidate_key(original_name)
                    ),
                    None,
                )
            if source_item is None:
                continue
            name = str(verdict.get("name") or source_item["name"]).strip()
            if not _is_text_term_candidate(name):
                continue
            approved.append(
                {
                    **source_item,
                    "llm_name": _preferred_knowledge_point_name(name),
                    "llm_aliases": [
                        str(alias).strip()
                        for alias in verdict.get("aliases", [])
                        if str(alias or "").strip()
                    ],
                    "llm_description": _sanitize_explanation_text(
                        str(verdict.get("description") or ""), 700
                    )
                    or (source_item.get("evidence") or [""])[0],
                    "llm_priority": int(verdict.get("priority") or source_item.get("priority_hint") or 2),
                    "llm_reason": str(verdict.get("reason") or "").strip(),
                }
            )
            if len(approved) >= limit:
                return approved
    return approved[:limit]


_KNOWLEDGE_POINT_REJECT_TYPES = {"meta", "person", "organization", "dataset", "symbol"}
_KNOWLEDGE_POINT_NOISE_RE = re.compile(
    r"("
    r"^doc-|"
    r"\.(pdf|docx?|pptx?|png|jpe?g|html?)$|"
    r"^(figure|fig|table|chapter|section|page|slide|appendix)\b|"
    r"^(图|表|第?\d+[章节页]|例题|习题|参考文献|目录)$|"
    r"https?://|www\.|"
    r"chunk|entity_name|source_id"
    r")",
    re.IGNORECASE,
)


def _is_probably_knowledge_point_label(label: str, node: dict, degree: int) -> bool:
    text = str(label or "").strip()
    if not text:
        return False
    normalized = _normalize_alias_key(text)
    if not normalized:
        return False
    if len(text) > 60:
        return False
    if _KNOWLEDGE_POINT_NOISE_RE.search(text):
        return False
    if re.fullmatch(r"[\d\s.,;:!?()\[\]{}<>+\-*/=_%|&]+", text):
        return False
    if text.count(" ") >= 8:
        return False
    if re.search(r"[。！？!?；;：:，,]\s*.", text) and len(text) > 18:
        return False

    node_type = str(node.get("type") or "").lower()
    if node_type in _KNOWLEDGE_POINT_REJECT_TYPES and not _knowledge_point_alias_keys(text):
        return False

    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_count = len(re.findall(r"[A-Za-z]", text))
    known_alias = bool(_knowledge_point_alias_keys(text) & set(_ENGLISH_TO_CHINESE_KP_ALIASES))
    has_mixed_term = bool(_mixed_cjk_english_alias_keys(text))

    if cjk_count >= 2:
        return True
    if has_mixed_term or known_alias:
        return True
    if ascii_count >= 3 and degree > 0 and len(text.split()) <= 5:
        return True
    return False


async def _sync_material_knowledge_points_once(
    material_id: int,
    limit: int = 24,
    refresh_existing: bool = False,
    use_llm_filter: bool = False,
) -> dict:
    db = SessionLocal()
    try:
        material = db.query(CourseMaterial).filter(CourseMaterial.id == material_id).first()
        if not material or not material.kb_name:
            return {"created": 0, "updated": 0}

        kb_dir = _kb_base_dir / material.kb_name
        rag_storage_dir = kb_dir / "rag_storage"
        entities_file = rag_storage_dir / "kv_store_full_entities.json"
        relations_file = rag_storage_dir / "kv_store_full_relations.json"
        if not entities_file.exists() or not relations_file.exists():
            return {"created": 0, "updated": 0}

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
        node_map = {str(node.get("id") or ""): node for node in nodes}
        relation_labels: dict[str, list[str]] = {}
        for edge in graph_payload.get("edges", []):
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source and target:
                target_label = str(node_map.get(target, {}).get("label") or target)
                source_label = str(node_map.get(source, {}).get("label") or source)
                relation_labels.setdefault(source, []).append(target_label)
                relation_labels.setdefault(target, []).append(source_label)

        existing_points_by_key: dict[str, KnowledgePoint] = {}
        existing_points_by_name: dict[str, KnowledgePoint] = {}
        existing_records = (
            db.query(KnowledgePoint)
            .filter(
                KnowledgePoint.course_id == material.course_id,
                KnowledgePoint.chapter_id == material.chapter_id,
            )
            .all()
        )
        for point in existing_records:
            existing_points_by_name.setdefault(_normalize_alias_key(point.name), point)
            for key in _knowledge_point_alias_keys(point.name):
                current = existing_points_by_key.get(key)
                if current is None or (
                    _contains_cjk(point.name) and not _contains_cjk(current.name)
                ):
                    existing_points_by_key[key] = point
            for alias in point.aliases or []:
                for key in _knowledge_point_alias_keys(alias.alias_name) | {
                    _normalize_alias_key(alias.alias_name)
                }:
                    if key:
                        existing_points_by_key.setdefault(key, point)
        candidates_by_key: dict[str, dict] = {}
        _collect_graph_teaching_candidates(
            kb_dir,
            nodes,
            relation_labels,
            material,
            candidates_by_key,
            limit=limit,
        )
        _collect_text_store_candidates(kb_dir, candidates_by_key)
        _collect_content_list_candidates(kb_dir, candidates_by_key)
        _collect_numbered_item_candidates(kb_dir, candidates_by_key)
        candidates = sorted(
            candidates_by_key.values(),
            key=lambda item: (
                int(item.get("priority_hint") or 0),
                int(item.get("degree") or 0),
                len(item.get("sources") or []),
            ),
            reverse=True,
        )[: max(limit * 4, 24)]
        approved_items = await _llm_filter_teaching_knowledge_points(
            candidates,
            material,
            limit=limit,
            use_llm=use_llm_filter,
        )
        skip_ai_duplicate_check = any(item.get("llm_unavailable") for item in approved_items)

        created = 0
        updated = 0
        for item in approved_items:
            display_name = _preferred_knowledge_point_name(
                str(item.get("llm_name") or item.get("name") or "")
            )
            if not display_name:
                continue
            node = item.get("node") if isinstance(item.get("node"), dict) else {}
            raw_names = [str(name) for name in item.get("raw_names", []) if str(name).strip()]
            alias_names = list(
                dict.fromkeys(
                    [
                        *raw_names,
                        *[str(alias) for alias in item.get("aliases", []) if str(alias).strip()],
                        *[str(alias) for alias in item.get("llm_aliases", []) if str(alias).strip()],
                    ]
                )
            )
            alias_keys = _knowledge_point_alias_keys(display_name)
            for alias in alias_names:
                alias_keys.update(_knowledge_point_alias_keys(alias))
                normalized_alias = _normalize_alias_key(alias)
                if normalized_alias:
                    alias_keys.add(normalized_alias)
            priority = max(1, min(5, int(item.get("llm_priority") or item.get("priority_hint") or 2)))
            description = _sanitize_explanation_text(
                str(item.get("llm_description") or ""), 700
            ) or _sanitize_explanation_text(" ".join(item.get("evidence") or []), 700)
            source_ref = (
                f"kb:{material.kb_name};"
                f"sources:{','.join(item.get('sources') or [])};"
                f"candidate:{item.get('name')};"
                f"method:teaching_point_llm_filter"
            )
            existing = next(
                (existing_points_by_key[key] for key in alias_keys if key in existing_points_by_key),
                None,
            )
            ai_verdict = None
            if existing is None and existing_records and not skip_ai_duplicate_check:
                existing, ai_verdict = await _find_duplicate_point_with_ai(
                    db,
                    display_name,
                    description,
                    existing_records,
                )
            if existing:
                for alias in alias_names:
                    _record_knowledge_point_alias(
                        db,
                        existing,
                        alias,
                        source="llm" if alias in (item.get("llm_aliases") or []) else "extractor",
                        confidence=0.86,
                        reason=item.get("llm_reason") or "Merged from generated knowledge point aliases",
                    )
                if ai_verdict:
                    _record_knowledge_point_alias(
                        db,
                        existing,
                        ai_verdict.get("alias_name") or display_name,
                        source="llm",
                        confidence=float(ai_verdict.get("confidence") or 0.0),
                        reason=ai_verdict.get("reason") or "",
                    )
                    canonical_name = str(ai_verdict.get("canonical_name") or "").strip()
                    if (
                        refresh_existing
                        and canonical_name
                        and not existing.is_confirmed
                        and not _find_knowledge_point_by_alias(
                            db,
                            existing.course_id,
                            existing.chapter_id,
                            canonical_name,
                            exclude_id=existing.id,
                        )
                    ):
                        existing.name = canonical_name
                if refresh_existing and not existing.is_confirmed:
                    if not ai_verdict and display_name and display_name != existing.name:
                        name_conflict = existing_points_by_name.get(_normalize_alias_key(display_name))
                        if not name_conflict or name_conflict.id == existing.id:
                            existing.name = display_name
                            existing_points_by_name[_normalize_alias_key(display_name)] = existing
                    existing.description = description
                    existing.priority = priority
                    existing.source_material_id = material.id
                    existing.source_type = material.source_type
                    existing.source_ref = source_ref
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                continue
            point = KnowledgePoint(
                course_id=material.course_id,
                chapter_id=material.chapter_id,
                source_material_id=material.id,
                created_by_teacher_id=material.course.teacher_id if material.course else None,
                name=display_name,
                description=description,
                priority=priority,
                source_type=material.source_type,
                source_ref=source_ref,
                is_confirmed=False,
            )
            db.add(point)
            db.flush()
            for alias in alias_names:
                _record_knowledge_point_alias(
                    db,
                    point,
                    str(alias),
                    source="llm" if alias in (item.get("llm_aliases") or []) else "extractor",
                    confidence=0.86,
                    reason=item.get("llm_reason") or "Alias merged during knowledge point extraction",
                )
            for alias in node.get("aliases", []) or []:
                _record_knowledge_point_alias(
                    db,
                    point,
                    str(alias),
                    source="graph",
                    confidence=0.9,
                    reason="Alias merged from canonical graph node",
                )
            for key in alias_keys:
                existing_points_by_key.setdefault(key, point)
            existing_records.append(point)
            created += 1
            if created >= limit:
                break

        if created or updated:
            db.commit()
        return {"created": created, "updated": updated}
    except OperationalError as exc:
        db.rollback()
        if "database is locked" in str(exc).lower():
            raise
        logger.exception("Failed to sync knowledge points for material_id=%s", material_id)
        return {"created": 0, "updated": 0}
    except Exception:
        logger.exception("Failed to sync knowledge points for material_id=%s", material_id)
        db.rollback()
        return {"created": 0, "updated": 0}
    finally:
        db.close()


async def _sync_material_knowledge_points(
    material_id: int,
    limit: int = 24,
    refresh_existing: bool = False,
    use_llm_filter: bool = False,
) -> dict:
    for attempt in range(3):
        try:
            return await _sync_material_knowledge_points_once(
                material_id,
                limit=limit,
                refresh_existing=refresh_existing,
                use_llm_filter=use_llm_filter,
            )
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower():
                raise
            if attempt >= 2:
                logger.exception("Database stayed locked while syncing material_id=%s", material_id)
                return {"created": 0, "updated": 0, "error": "database_locked"}
            await asyncio.sleep(1.5 * (attempt + 1))
    return {"created": 0, "updated": 0}


async def _run_course_material_initialization_task(
    material_id: int,
    initializer: KnowledgeBaseInitializer,
) -> None:
    _set_material_parse_status(material_id, "parsing")
    await run_initialization_task(initializer)
    if is_knowledge_base_initialized(initializer.kb_name):
        await generate_node_explanation_cache(initializer.kb_name, use_llm=False, refresh=False)
        await _sync_material_knowledge_points(material_id)
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
        await generate_node_explanation_cache(kb_name, use_llm=False, refresh=False)
        await _sync_material_knowledge_points(material_id)
    _set_material_parse_status(
        material_id,
        "parsed" if is_knowledge_base_initialized(kb_name) else "failed",
    )


async def _run_course_material_rebuild_task(
    material_ids: list[int],
    initializer: KnowledgeBaseInitializer,
) -> None:
    for material_id in material_ids:
        _set_material_parse_status(material_id, "parsing")
    await run_initialization_task(initializer)
    initialized = is_knowledge_base_initialized(initializer.kb_name)
    if initialized:
        await generate_node_explanation_cache(initializer.kb_name, use_llm=False, refresh=False)
        for material_id in material_ids:
            await _sync_material_knowledge_points(material_id)
    for material_id in material_ids:
        _set_material_parse_status(material_id, "parsed" if initialized else "failed")


def _enqueue_course_kb_rebuild(
    background_tasks: BackgroundTasks,
    kb_name: str | None,
    remaining_materials: list[CourseMaterial],
) -> None:
    if not kb_name:
        return

    _delete_knowledge_base_storage(kb_name)
    rebuild_materials = [
        material
        for material in remaining_materials
        if material.file_path and Path(material.file_path).is_file()
    ]
    if not rebuild_materials:
        return

    try:
        llm_config = get_llm_config()
        provider = normalize_rag_provider(rebuild_materials[0].rag_provider)
        manager = get_kb_manager()
        manager.update_kb_status(
            name=kb_name,
            status="initializing",
            progress={
                "stage": "initializing",
                "message": "Rebuilding course knowledge base after material deletion...",
                "percent": 0,
                "current": 0,
                "total": len(rebuild_materials),
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
        first = rebuild_materials[0]
        _write_course_kb_metadata(
            kb_name=kb_name,
            material_id=first.id,
            display_name=first.title or first.original_filename or kb_name,
            course_id=first.course_id,
            chapter_id=first.chapter_id,
            source_type=first.source_type,
            rag_provider=provider,
        )
        metadata_file = _kb_base_dir / kb_name / "metadata.json"
        try:
            metadata = _safe_read_json(metadata_file)
            if isinstance(metadata, dict):
                metadata["material_ids"] = [material.id for material in rebuild_materials]
                metadata["display_name"] = first.chapter.title if first.chapter else first.course.name
                with open(metadata_file, "w", encoding="utf-8") as fp:
                    json.dump(metadata, fp, indent=2, ensure_ascii=False)
        except Exception:
            pass

        for material in rebuild_materials:
            target = initializer.raw_dir / Path(material.file_path).name
            if not target.exists():
                shutil.copyfile(material.file_path, target)

        progress_tracker.update(
            ProgressStage.PROCESSING_DOCUMENTS,
            "Saved remaining course materials, preparing to rebuild...",
            current=0,
            total=len(rebuild_materials),
        )
        background_tasks.add_task(
            _run_course_material_rebuild_task,
            [material.id for material in rebuild_materials],
            initializer,
        )
    except Exception:
        for material in rebuild_materials:
            _set_material_parse_status(material.id, "failed")


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
        kb_name=request.kb_name
        or _unique_course_material_kb_name(db, request.original_filename or title),
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

    kb_name = _unique_course_material_kb_name(db, file.filename or clean_title)
    _reset_stale_course_kb_if_unreferenced(db, kb_name)
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
        if not material.kb_name:
            material.kb_name = _unique_course_material_kb_name(
                db,
                material.original_filename or material.title,
            )
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
    background_tasks: BackgroundTasks,
    operator_username: str,
    db: Session = Depends(get_db),
):
    material = _get_material(db, material_id)
    _ensure_material_operator(db, operator_username, material)
    kb_name = material.kb_name
    file_path = material.file_path
    remaining_materials = (
        db.query(CourseMaterial)
        .filter(CourseMaterial.kb_name == kb_name, CourseMaterial.id != material.id)
        .order_by(CourseMaterial.created_at.asc())
        .all()
        if kb_name
        else []
    )
    point_ids = [
        point_id
        for (point_id,) in db.query(KnowledgePoint.id)
        .filter(KnowledgePoint.source_material_id == material.id)
        .all()
    ]
    _delete_knowledge_points_with_records(db, point_ids)
    db.delete(material)
    db.commit()
    _delete_material_file(file_path)
    _enqueue_course_kb_rebuild(background_tasks, kb_name, remaining_materials)
    return {"success": True}


@router.post("/materials/{material_id}/knowledge-points/sync")
async def sync_material_knowledge_points(
    material_id: int,
    teacher_username: str,
    refresh_existing: bool = True,
    db: Session = Depends(get_db),
):
    teacher = _get_teacher_by_username(db, teacher_username)
    material = _get_material(db, material_id)
    _ensure_teacher_owns_course(teacher, material.course)

    if not material.kb_name:
        raise HTTPException(status_code=400, detail="该资料尚未关联可解析的知识图谱")
    if not is_knowledge_base_initialized(material.kb_name):
        raise HTTPException(status_code=400, detail="资料仍在解析中，完成后才能生成知识点")

    await generate_node_explanation_cache(material.kb_name, use_llm=False, refresh=False)
    result = await _sync_material_knowledge_points(material.id, refresh_existing=refresh_existing)
    if result.get("error") == "database_locked":
        raise HTTPException(status_code=503, detail="数据库正忙，请稍后再试")
    created = result["created"]
    updated = result["updated"]
    return {
        "success": True,
        "created_count": created,
        "updated_count": updated,
        "message": (
            f"已生成 {created} 个候选知识点，更新 {updated} 个未确认解释"
            if created or updated
            else "没有新的候选知识点可生成"
        ),
    }


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
    points = _dedupe_knowledge_points(points)

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

    clean_name = request.name.strip()
    existing = _find_knowledge_point_by_alias(db, course.id, request.chapter_id, clean_name)
    if existing:
        if request.description.strip() and not existing.description:
            existing.description = request.description.strip()
        if request.priority > existing.priority:
            existing.priority = request.priority
        if request.is_confirmed and not existing.is_confirmed:
            existing.is_confirmed = True
        if request.source_material_id and not existing.source_material_id:
            existing.source_material_id = request.source_material_id
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return {"success": True, "knowledge_point": _knowledge_point_payload(existing)}

    point = KnowledgePoint(
        course_id=course.id,
        chapter_id=request.chapter_id,
        source_material_id=request.source_material_id,
        created_by_teacher_id=teacher.id,
        name=clean_name,
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
        clean_name = request.name.strip()
        existing = _find_knowledge_point_by_alias(
            db,
            point.course_id,
            point.chapter_id,
            clean_name,
            exclude_id=point.id,
        )
        if existing:
            raise HTTPException(status_code=400, detail="该章节下已存在同义知识点")
        point.name = clean_name
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
