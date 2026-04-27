from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Literal

from sqlalchemy.orm import Session

from src.core.models import KnowledgeMasteryEvent, KnowledgePoint, StudentKnowledgeMastery

DifficultyLevel = Literal["easy", "medium", "hard"]
AnswerQuality = Literal["independent", "hinted", "multi_attempt", "partial", "wrong"]

DIFFICULTY_FACTORS: dict[str, float] = {
    "easy": 0.7,
    "basic": 0.7,
    "medium": 1.0,
    "normal": 1.0,
    "hard": 1.3,
    "difficult": 1.3,
}

QUALITY_FACTORS: dict[str, float] = {
    "independent": 1.0,
    "hinted": 0.5,
    "multi_attempt": 0.4,
    "partial": 0.5,
    "wrong": 1.0,
}

PRIORITY_FACTORS: dict[int, float] = {
    5: 1.2,
    4: 1.1,
    3: 1.0,
    2: 0.9,
    1: 0.8,
}


@dataclass
class MasteryUpdateResult:
    event: KnowledgeMasteryEvent
    mastery: StudentKnowledgeMastery
    details: dict


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def normalize_difficulty(value: str | None) -> str:
    normalized = (value or "medium").strip().lower()
    return normalized if normalized in DIFFICULTY_FACTORS else "medium"


def _score_ratio(score: float | None, max_score: float | None) -> float | None:
    if score is None or not max_score or max_score <= 0:
        return None
    return _clamp(float(score) / float(max_score), 0.0, 1.0)


def infer_correctness(
    *,
    is_correct: bool | None,
    score: float | None,
    max_score: float | None,
) -> bool | None:
    if is_correct is not None:
        return is_correct
    ratio = _score_ratio(score, max_score)
    if ratio is None:
        return None
    if ratio >= 0.75:
        return True
    if ratio < 0.45:
        return False
    return None


def infer_answer_quality(
    *,
    is_correct: bool | None,
    score: float | None,
    max_score: float | None,
    used_hint: bool = False,
    attempt_count: int | None = None,
    answer_quality: str | None = None,
) -> tuple[str, float]:
    explicit = (answer_quality or "").strip().lower()
    if explicit in QUALITY_FACTORS:
        if explicit == "partial":
            ratio = _score_ratio(score, max_score)
            return explicit, _clamp(ratio if ratio is not None else 0.5, 0.3, 0.7)
        return explicit, QUALITY_FACTORS[explicit]

    if is_correct is True:
        if used_hint:
            return "hinted", QUALITY_FACTORS["hinted"]
        if attempt_count and attempt_count > 1:
            return "multi_attempt", QUALITY_FACTORS["multi_attempt"]
        return "independent", QUALITY_FACTORS["independent"]

    if is_correct is False:
        return "wrong", QUALITY_FACTORS["wrong"]

    ratio = _score_ratio(score, max_score)
    if ratio is not None:
        return "partial", _clamp(ratio, 0.3, 0.7)
    return "partial", QUALITY_FACTORS["partial"]


def _streak_adjustment(
    db: Session,
    *,
    student_id: int,
    knowledge_point_id: int,
    is_correct: bool | None,
) -> tuple[float, int, str | None]:
    if is_correct is None:
        return 0.0, 0, None

    recent = (
        db.query(KnowledgeMasteryEvent)
        .filter(
            KnowledgeMasteryEvent.student_id == student_id,
            KnowledgeMasteryEvent.knowledge_point_id == knowledge_point_id,
            KnowledgeMasteryEvent.is_correct.isnot(None),
        )
        .order_by(KnowledgeMasteryEvent.created_at.desc())
        .limit(3)
        .all()
    )

    previous_same = 0
    for event in recent:
        if event.is_correct == is_correct:
            previous_same += 1
        else:
            break

    streak_after = previous_same + 1
    if is_correct:
        if streak_after >= 3:
            return 0.05, streak_after, "continuous_correct_3_plus"
        if streak_after == 2:
            return 0.03, streak_after, "continuous_correct_2"
        return 0.0, streak_after, None

    if streak_after >= 3:
        return -0.03, streak_after, "continuous_wrong_3_plus"
    if streak_after == 2:
        return -0.02, streak_after, "continuous_wrong_2"
    return 0.0, streak_after, None


def _knowledge_priority_factor(
    db: Session,
    *,
    knowledge_point_id: int,
) -> tuple[int, float]:
    point = db.query(KnowledgePoint).filter(KnowledgePoint.id == knowledge_point_id).first()
    priority = int(getattr(point, "priority", 3) or 3) if point else 3
    priority = int(_clamp(priority, 1, 5))
    return priority, PRIORITY_FACTORS.get(priority, 1.0)


def calculate_mastery_delta(
    db: Session,
    *,
    student_id: int,
    knowledge_point_id: int,
    source_type: str,
    difficulty: str | None = "medium",
    answer_quality: str | None = None,
    used_hint: bool = False,
    attempt_count: int | None = None,
    score: float | None = None,
    max_score: float | None = None,
    is_correct: bool | None = None,
    mastery_delta: float | None = None,
) -> tuple[float, bool | None, dict]:
    normalized_correct = infer_correctness(
        is_correct=is_correct,
        score=score,
        max_score=max_score,
    )
    normalized_difficulty = normalize_difficulty(difficulty)
    difficulty_factor = DIFFICULTY_FACTORS[normalized_difficulty]
    priority, priority_factor = _knowledge_priority_factor(
        db,
        knowledge_point_id=knowledge_point_id,
    )
    normalized_quality, quality_factor = infer_answer_quality(
        is_correct=normalized_correct,
        score=score,
        max_score=max_score,
        used_hint=used_hint,
        attempt_count=attempt_count,
        answer_quality=answer_quality,
    )

    if mastery_delta is not None:
        base_delta = _clamp(float(mastery_delta), -1.0, 1.0)
        streak_delta, streak_count, streak_label = 0.0, 0, None
    else:
        if normalized_correct is True:
            base = 0.10
        elif normalized_correct is False:
            base = -0.04
        else:
            ratio = _score_ratio(score, max_score)
            base = 0.05 if ratio is None else 0.08 * _clamp(ratio, 0.25, 0.75)

        base_delta = base * difficulty_factor * quality_factor * priority_factor
        streak_delta, streak_count, streak_label = _streak_adjustment(
            db,
            student_id=student_id,
            knowledge_point_id=knowledge_point_id,
            is_correct=normalized_correct,
        )

    total_delta = round(_clamp(base_delta + streak_delta, -1.0, 1.0), 4)
    details = {
        "source_type": source_type,
        "difficulty": normalized_difficulty,
        "difficulty_factor": difficulty_factor,
        "knowledge_priority": priority,
        "priority_factor": priority_factor,
        "answer_quality": normalized_quality,
        "quality_factor": round(quality_factor, 3),
        "base_delta": round(base_delta, 4),
        "streak_delta": round(streak_delta, 4),
        "streak_count": streak_count,
        "streak_label": streak_label,
        "used_hint": bool(used_hint),
        "attempt_count": attempt_count,
    }
    return total_delta, normalized_correct, details


def apply_mastery_event(
    db: Session,
    *,
    student_id: int,
    knowledge_point_id: int,
    source_type: str,
    source_id: str | None = None,
    difficulty: str | None = "medium",
    answer_quality: str | None = None,
    used_hint: bool = False,
    attempt_count: int | None = None,
    score: float | None = None,
    max_score: float | None = None,
    is_correct: bool | None = None,
    mastery_delta: float | None = None,
    note: str = "",
) -> MasteryUpdateResult:
    delta, normalized_correct, details = calculate_mastery_delta(
        db,
        student_id=student_id,
        knowledge_point_id=knowledge_point_id,
        source_type=source_type,
        difficulty=difficulty,
        answer_quality=answer_quality,
        used_hint=used_hint,
        attempt_count=attempt_count,
        score=score,
        max_score=max_score,
        is_correct=is_correct,
        mastery_delta=mastery_delta,
    )

    mastery = (
        db.query(StudentKnowledgeMastery)
        .filter(
            StudentKnowledgeMastery.student_id == student_id,
            StudentKnowledgeMastery.knowledge_point_id == knowledge_point_id,
        )
        .first()
    )
    if not mastery:
        mastery = StudentKnowledgeMastery(
            student_id=student_id,
            knowledge_point_id=knowledge_point_id,
            mastery_level=0.0,
            correct_count=0,
            wrong_count=0,
            practice_count=0,
        )
        db.add(mastery)

    now = datetime.utcnow()
    mastery.mastery_level = _clamp(float(mastery.mastery_level or 0.0) + delta, 0.0, 1.0)
    mastery.practice_count = int(mastery.practice_count or 0) + 1
    if normalized_correct is True:
        mastery.correct_count = int(mastery.correct_count or 0) + 1
    elif normalized_correct is False:
        mastery.wrong_count = int(mastery.wrong_count or 0) + 1
    mastery.last_practiced_at = now
    mastery.updated_at = now

    clean_note = (note or "").strip()
    metadata = json.dumps({"mastery_strategy": details}, ensure_ascii=False)
    event_note = f"{clean_note}\n{metadata}".strip() if clean_note else metadata
    event = KnowledgeMasteryEvent(
        student_id=student_id,
        knowledge_point_id=knowledge_point_id,
        source_type=source_type,
        source_id=source_id,
        score=score,
        max_score=max_score,
        is_correct=normalized_correct,
        mastery_delta=delta,
        note=event_note,
    )
    db.add(event)
    db.flush()
    return MasteryUpdateResult(event=event, mastery=mastery, details=details)
