from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.models import AssignmentScore, Student, Teacher, User

router = APIRouter()


@router.get("/students")
async def get_all_students(db: Session = Depends(get_db)):
    students = db.query(Student).all()

    result = []
    for student in students:
        user = db.query(User).filter(User.id == student.user_id).first()
        result.append(
            {
                "id": student.id,
                "username": user.username if user else None,
                "email": user.email if user else None,
                "real_name": student.real_name,
                "student_no": student.student_no,
                "grade_name": student.grade_name,
                "class_name": student.class_name,
                "major": student.major,
            }
        )

    return {"students": result}


@router.get("/students/{student_id}")
async def get_student_detail(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    user = db.query(User).filter(User.id == student.user_id).first()

    return {
        "student": {
            "id": student.id,
            "username": user.username if user else None,
            "email": user.email if user else None,
            "real_name": student.real_name,
            "student_no": student.student_no,
            "grade_name": student.grade_name,
            "class_name": student.class_name,
            "major": student.major,
        }
    }


@router.get("/students/{student_id}/scores")
async def get_student_scores_for_teacher(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    scores = (
        db.query(AssignmentScore)
        .filter(AssignmentScore.student_id == student.id)
        .order_by(AssignmentScore.assignment_no.asc())
        .all()
    )

    result = []
    for s in scores:
        teacher_name = None
        if s.graded_by:
            teacher = db.query(Teacher).filter(Teacher.id == s.graded_by).first()
            if teacher:
                teacher_name = teacher.real_name

        result.append(
            {
                "id": s.id,
                "assignment_no": s.assignment_no,
                "assignment_title": s.assignment_title,
                "score": s.score,
                "feedback": s.feedback,
                "graded_by": s.graded_by,
                "graded_by_name": teacher_name,
                "graded_at": s.graded_at,
            }
        )

    return {
        "student": {
            "id": student.id,
            "real_name": student.real_name,
            "student_no": student.student_no,
            "grade_name": student.grade_name,
            "class_name": student.class_name,
        },
        "scores": result,
    }


@router.post("/scores/add")
async def add_student_score(
    payload: dict,
    db: Session = Depends(get_db),
):
    student_id = payload.get("student_id")
    assignment_no = payload.get("assignment_no")
    assignment_title = payload.get("assignment_title")
    score = payload.get("score")
    feedback = payload.get("feedback")
    graded_by = payload.get("graded_by")

    if not student_id or assignment_no is None or score is None:
        raise HTTPException(status_code=400, detail="student_id、assignment_no、score 为必填项")

    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    existing = (
        db.query(AssignmentScore)
        .filter(
            AssignmentScore.student_id == student_id,
            AssignmentScore.assignment_no == assignment_no,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="该学生该次作业成绩已存在")

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

    return {
        "success": True,
        "message": "成绩添加成功",
        "score": {
            "id": new_score.id,
            "student_id": new_score.student_id,
            "assignment_no": new_score.assignment_no,
            "assignment_title": new_score.assignment_title,
            "score": new_score.score,
            "feedback": new_score.feedback,
            "graded_by": new_score.graded_by,
            "graded_at": new_score.graded_at,
        },
    }