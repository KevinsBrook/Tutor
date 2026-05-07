from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.models import (
    AssignmentScore,
    Student,
    Teacher,
    User,
    ExperimentSubmission,
    ExperimentQuestion,
    ExperimentAnswer,
)

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

@router.get("/students/{student_id}/experiment-answers")
async def get_student_experiment_answers_for_teacher(
    student_id: int,
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.id == student_id).first()

    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    user = db.query(User).filter(User.id == student.user_id).first()

    submissions = (
        db.query(ExperimentSubmission)
        .filter(ExperimentSubmission.student_id == student.id)
        .order_by(
            ExperimentSubmission.assignment_no.asc(),
            ExperimentSubmission.created_at.desc(),
        )
        .all()
    )

    submission_result = []

    for submission in submissions:
        questions = (
            db.query(ExperimentQuestion)
            .filter(ExperimentQuestion.submission_id == submission.id)
            .order_by(ExperimentQuestion.question_no.asc())
            .all()
        )

        question_result = []
        total_score_sum = 0
        scored_count = 0
        answer_count = 0

        for q in questions:
            answers = (
                db.query(ExperimentAnswer)
                .filter(
                    ExperimentAnswer.question_id == q.id,
                    ExperimentAnswer.student_id == student.id,
                )
                .order_by(ExperimentAnswer.created_at.desc())
                .all()
            )

            answer_items = []

            for a in answers:
                answer_count += 1

                if a.total_score is not None:
                    total_score_sum += a.total_score
                    scored_count += 1

                answer_items.append(
                    {
                        "id": a.id,
                        "answer_text": a.answer_text,
                        "score_code_understanding": a.score_code_understanding,
                        "score_concept_mastery": a.score_concept_mastery,
                        "score_question_response": a.score_question_response,
                        "total_score": a.total_score,
                        "feedback": a.feedback,
                        "grading_reason": a.grading_reason,
                        "created_at": a.created_at,
                    }
                )

            question_result.append(
                {
                    "question_id": q.id,
                    "question_no": q.question_no,
                    "question_text": q.question_text,
                    "reference_points": q.reference_points,
                    "answers": answer_items,
                }
            )

        question_count = len(questions)

        average_score = (
            round(total_score_sum / question_count, 2)
            if question_count > 0
            else None
        )

        submission_result.append(
            {
                "id": submission.id,
                "assignment_no": submission.assignment_no,
                "experiment_title": submission.experiment_title,
                "original_filename": submission.original_filename,
                "status": submission.status,
                "created_at": submission.created_at,
                "question_started_at": submission.question_started_at,
                "answer_deadline_at": submission.answer_deadline_at,
                "report_text_preview": (submission.report_text or "")[:300],
                "report_text_length": len(submission.report_text or ""),
                "question_count": len(questions),
                "answer_count": answer_count,
                "average_score": average_score,
                "questions": question_result,
            }
        )

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
        },
        "submissions": submission_result,
    }