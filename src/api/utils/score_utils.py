from sqlalchemy.orm import Session
from src.core.models import AssignmentScore


def upsert_assignment_score(
    db: Session,
    student_id: int,
    assignment_no: int,
    score: float,
    assignment_title: str | None = None,
    feedback: str | None = None,
    graded_by: int | None = None,
):
    existing = (
        db.query(AssignmentScore)
        .filter(
            AssignmentScore.student_id == student_id,
            AssignmentScore.assignment_no == assignment_no,
        )
        .first()
    )

    if existing:
        existing.score = score
        existing.assignment_title = assignment_title
        existing.feedback = feedback
        existing.graded_by = graded_by
        db.commit()
        db.refresh(existing)
        return existing

    new_score = AssignmentScore(
        student_id=student_id,
        assignment_no=assignment_no,
        assignment_title=assignment_title,
        score=score,
        feedback=feedback,
        graded_by=graded_by,
    )
    db.add(new_score)
    db.commit()
    db.refresh(new_score)
    return new_score