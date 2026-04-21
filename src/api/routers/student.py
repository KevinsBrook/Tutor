from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.models import AssignmentScore, Student, User

router = APIRouter()


@router.get("/me/{username}")
async def get_student_me(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.role == "student").first()
    if not user:
        raise HTTPException(status_code=404, detail="学生用户不存在")

    student = db.query(Student).filter(Student.user_id == user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生信息不存在")

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        },
        "student": {
            "id": student.id,
            "real_name": student.real_name,
            "student_no": student.student_no,
            "grade_name": student.grade_name,
            "class_name": student.class_name,
            "major": student.major,
        },
    }


@router.get("/scores/{username}")
async def get_student_scores(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.role == "student").first()
    if not user:
        raise HTTPException(status_code=404, detail="学生用户不存在")

    student = db.query(Student).filter(Student.user_id == user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生信息不存在")

    scores = (
        db.query(AssignmentScore)
        .filter(AssignmentScore.student_id == student.id)
        .order_by(AssignmentScore.assignment_no.asc())
        .all()
    )

    return {
        "student": {
            "id": student.id,
            "real_name": student.real_name,
            "student_no": student.student_no,
            "grade_name": student.grade_name,
            "class_name": student.class_name,
        },
        "scores": [
            {
                "id": s.id,
                "assignment_no": s.assignment_no,
                "assignment_title": s.assignment_title,
                "score": s.score,
                "feedback": s.feedback,
                "graded_by": s.graded_by,
                "graded_at": s.graded_at,
            }
            for s in scores
        ],
    }