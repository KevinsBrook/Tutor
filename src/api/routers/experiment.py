import json
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from docx import Document
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy.orm import Session

from src.api.utils.score_utils import upsert_assignment_score
from src.core.database import get_db
from src.core.models import (
    ExperimentAnswer,
    ExperimentQuestion,
    ExperimentSubmission,
    Student,
    User,
)
from src.services.llm import get_llm_client

router = APIRouter()
class GenerateQuestionsRequest(BaseModel):
    submission_id: int
    question_count: int | None = None
class SubmitAnswerRequest(BaseModel):
    username: str
    question_id: int
    answer_text: str
    pause_count: int | None = None
    longest_pause_ms: int | None = None
    answer_duration_seconds: int | None = None
def build_question_prompt(report_text: str, experiment_title: str, question_count: int) -> str:
    return f"""
你是一名实验教学老师。请根据学生提交的实验报告内容，生成 {question_count} 个口头问答问题。

要求：
1. 问题必须紧扣实验报告内容；
2. 重点考察学生是否真正理解自己写的实验过程、原理、结果和结论；
3. 问题不要太空泛；
4. 每个问题后面给出“参考要点”；
5. 输出必须是 JSON 数组，不要输出任何额外说明。

输出格式严格如下：
[
  {{
    "question_no": 1,
    "question_text": "问题内容",
    "reference_points": "参考要点"
  }},
  {{
    "question_no": 2,
    "question_text": "问题内容",
    "reference_points": "参考要点"
  }}
]

实验标题：
{experiment_title}

实验报告内容：
{report_text[:6000]}
""".strip()


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_UPLOAD_DIR = PROJECT_ROOT / "data" / "experiment_reports"
EXPERIMENT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def extract_text_from_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    try:
        # 1. txt
        if suffix == ".txt":
            return file_path.read_text(encoding="utf-8", errors="ignore").strip()

        # 2. docx
        if suffix == ".docx":
            doc = Document(str(file_path))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs).strip()

        # 3. pdf
        if suffix == ".pdf":
            reader = PdfReader(str(file_path))
            pages_text = []

            for page in reader.pages:
                text = page.extract_text()
                if text and text.strip():
                    pages_text.append(text.strip())

            return "\n".join(pages_text).strip()

        # 4. 其他格式暂不支持
        return ""

    except Exception as e:
        print(f"[extract_text_from_file] 文件解析失败: {file_path.name}, error={e}")
        return ""
def build_grading_prompt(
    experiment_title: str,
    report_text: str,
    question_text: str,
    reference_points: str,
    answer_text: str,
    pause_count: int | None = None,
    longest_pause_ms: int | None = None,
    answer_duration_seconds: int | None = None,
) -> str:
    return f"""
你是一名实验教学评分老师。请根据学生实验报告、系统生成的问题、参考要点，以及学生的作答内容，对学生进行评分。

评分标准如下（满分 5 分）：
1. 代码理解：2 分
2. 概念掌握：1 分
3. 问题回答：2 分

要求：
1. 必须严格基于学生回答内容评分；
2. 分数不能超过各自上限；
3. 必须返回合法 JSON；
4. 不要输出任何解释、前言、后记、Markdown 代码块。

输出格式严格如下：
{{
  "score_code_understanding": 1.5,
  "score_concept_mastery": 1.0,
  "score_question_response": 1.5,
  "total_score": 4.0,
  "grading_reason": "逐项评分理由",
  "feedback": "给学生的简要反馈"
}}

【实验标题】
{experiment_title}

【实验报告内容】
{report_text[:4000]}

【问题】
{question_text}

【参考要点】
{reference_points}

【学生回答】
{answer_text}
【作答行为指标】
- 回答总时长（秒）：{answer_duration_seconds}
- 停顿次数：{pause_count}
- 最长停顿（毫秒）：{longest_pause_ms}

评分要求补充：
1. 可以把停顿情况作为“表达流畅度”的参考，但不能压倒知识内容本身；
2. 如果学生内容正确但有少量停顿，不应严重扣分；
3. 如果频繁长时间停顿、内容断裂明显，可以在“问题回答”部分适度扣分；
""".strip()

@router.post("/upload-report")
async def upload_experiment_report(
    username: str = Form(...),
    assignment_no: int = Form(...),
    experiment_title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username, User.role == "student").first()
    if not user:
        raise HTTPException(status_code=404, detail="学生用户不存在")

    student = db.query(Student).filter(Student.user_id == user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生信息不存在")

    if not file.filename:
        raise HTTPException(status_code=400, detail="未检测到上传文件")
    allowed_suffixes = {".txt", ".docx", ".pdf"}
    suffix = Path(file.filename).suffix.lower()

    if suffix not in allowed_suffixes:
      raise HTTPException(status_code=400, detail="当前仅支持上传 txt、docx、pdf 文件")
    
    student_dir = EXPERIMENT_UPLOAD_DIR / student.student_no
    student_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_filename = f"{assignment_no}_{timestamp}_{file.filename}"
    save_path = student_dir / safe_filename

    with save_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    report_text = extract_text_from_file(save_path)

    submission = ExperimentSubmission(
        student_id=student.id,
        assignment_no=assignment_no,
        experiment_title=experiment_title,
        original_filename=file.filename,
        report_file_path=str(save_path),
        report_text=report_text,
        status="parsed" if report_text else "uploaded",
    )

    db.add(submission)
    db.commit()
    db.refresh(submission)

    return {
        "success": True,
        "message": "实验报告上传成功",
        "submission": {
            "id": submission.id,
            "student_id": submission.student_id,
            "assignment_no": submission.assignment_no,
            "experiment_title": submission.experiment_title,
            "original_filename": submission.original_filename,
            "report_file_path": submission.report_file_path,
            "status": submission.status,
            "created_at": submission.created_at,
            "text_extracted": bool(submission.report_text and submission.report_text.strip()),
            "report_text_length": len(submission.report_text or ""),
            "report_text_preview": (submission.report_text or "")[:300],
            "question_started_at": submission.question_started_at,
            "answer_deadline_at": submission.answer_deadline_at,
        },
    }


@router.get("/my-submissions/{username}")
async def get_my_experiment_submissions(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.role == "student").first()
    if not user:
        raise HTTPException(status_code=404, detail="学生用户不存在")

    student = db.query(Student).filter(Student.user_id == user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生信息不存在")

    submissions = (
        db.query(ExperimentSubmission)
        .filter(ExperimentSubmission.student_id == student.id)
        .order_by(ExperimentSubmission.assignment_no.asc(), ExperimentSubmission.created_at.desc())
        .all()
    )

    return {
        "student": {
            "id": student.id,
            "real_name": student.real_name,
            "student_no": student.student_no,
        },
        "submissions": [
            {
                "id": item.id,
                "assignment_no": item.assignment_no,
                "experiment_title": item.experiment_title,
                "original_filename": item.original_filename,
                "status": item.status,
                "created_at": item.created_at,
            }
            for item in submissions
        ],
    }
@router.post("/generate-questions")
async def generate_experiment_questions(
    request: GenerateQuestionsRequest,
    db: Session = Depends(get_db),
):
    submission = (
        db.query(ExperimentSubmission)
        .filter(ExperimentSubmission.id == request.submission_id)
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="实验报告提交记录不存在")

    if not submission.report_text or not submission.report_text.strip():
        raise HTTPException(status_code=400, detail="实验报告文本为空，无法生成问题")

    # 如果已经生成过，先删掉旧问题，避免重复
    old_questions = (
        db.query(ExperimentQuestion)
        .filter(ExperimentQuestion.submission_id == submission.id)
        .all()
    )
    for q in old_questions:
        db.delete(q)
    db.commit()
    question_count = request.question_count or random.randint(4, 6)
    prompt = build_question_prompt(
        report_text=submission.report_text,
        experiment_title=submission.experiment_title,
        question_count=question_count,
    )

    try:
        llm_client = get_llm_client()

        result_text = await llm_client.complete(
            prompt=prompt,
            system_prompt="你是一名实验教学老师。请严格按照要求输出 JSON，不要输出解释，不要输出 Markdown 代码块。"
        )
        clean_text = result_text.strip()

        if clean_text.startswith("```json"):
            clean_text = clean_text[len("```json"):].strip()
        elif clean_text.startswith("```"):
            clean_text = clean_text[len("```"):].strip()

        if clean_text.endswith("```"):
            clean_text = clean_text[:-3].strip()

        try:
            parsed = json.loads(clean_text)
        except Exception:
            raise HTTPException(
                status_code=500,
                detail=f"模型返回的不是合法 JSON：{result_text[:300]}"
            )

        if not isinstance(parsed, list) or len(parsed) == 0:
            raise HTTPException(status_code=500, detail="模型未返回有效问题列表")

        saved_questions = []
        for idx, item in enumerate(parsed, start=1):
            question = ExperimentQuestion(
                submission_id=submission.id,
                question_no=item.get("question_no", idx),
                question_text=item.get("question_text", "").strip(),
                reference_points=item.get("reference_points", "").strip(),
            )
            db.add(question)
            db.flush()

            saved_questions.append(
                {
                    "id": question.id,
                    "question_no": question.question_no,
                    "question_text": question.question_text,
                    "reference_points": question.reference_points,
                }
            )

        submission.status = "questioned"
        submission.question_started_at = datetime.now()
        submission.answer_deadline_at = datetime.now() + timedelta(minutes=5)
        db.commit()

        return {
            "success": True,
            "message": "问题生成成功",
            "submission_id": submission.id,
            "question_count": len(saved_questions),
            "question_started_at": submission.question_started_at,
            "answer_deadline_at": submission.answer_deadline_at,
            "questions": saved_questions,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成问题失败：{str(e)}")
    
@router.get("/questions/{submission_id}")
async def get_submission_questions(submission_id: int, db: Session = Depends(get_db)):
    submission = (
        db.query(ExperimentSubmission)
        .filter(ExperimentSubmission.id == submission_id)
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="实验报告提交记录不存在")

    questions = (
        db.query(ExperimentQuestion)
        .filter(ExperimentQuestion.submission_id == submission_id)
        .order_by(ExperimentQuestion.question_no.asc())
        .all()
    )

    return {
        "submission": {
                "id": submission.id,
                "assignment_no": submission.assignment_no,
                "experiment_title": submission.experiment_title,
                "status": submission.status,
                "question_started_at": submission.question_started_at,
                "answer_deadline_at": submission.answer_deadline_at,
            },
        "questions": [
            {
                "id": q.id,
                "question_no": q.question_no,
                "question_text": q.question_text,
                "reference_points": q.reference_points,
            }
            for q in questions
        ],
    }

@router.post("/submit-answer")
async def submit_answer_and_grade(
    request: SubmitAnswerRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == request.username, User.role == "student").first()
    if not user:
        raise HTTPException(status_code=404, detail="学生用户不存在")

    student = db.query(Student).filter(Student.user_id == user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生信息不存在")

    question = (
        db.query(ExperimentQuestion)
        .filter(ExperimentQuestion.id == request.question_id)
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")

    submission = (
        db.query(ExperimentSubmission)
        .filter(ExperimentSubmission.id == question.submission_id)
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="对应实验报告不存在")

    if not request.answer_text.strip():
        raise HTTPException(status_code=400, detail="回答内容不能为空")

    prompt = build_grading_prompt(
        experiment_title=submission.experiment_title,
        report_text=submission.report_text or "",
        question_text=question.question_text,
        reference_points=question.reference_points or "",
        answer_text=request.answer_text,
        pause_count=request.pause_count,
        longest_pause_ms=request.longest_pause_ms,
        answer_duration_seconds=request.answer_duration_seconds,
    )

    try:
        llm_client = get_llm_client()

        result_text = await llm_client.complete(
            prompt=prompt,
            system_prompt="你是一名严格的实验教学评分老师。请严格按照要求输出 JSON。"
        )

        clean_text = result_text.strip()

        if clean_text.startswith("```json"):
            clean_text = clean_text[len("```json"):].strip()
        elif clean_text.startswith("```"):
            clean_text = clean_text[len("```"):].strip()

        if clean_text.endswith("```"):
            clean_text = clean_text[:-3].strip()

        try:
            parsed = json.loads(clean_text)
        except Exception:
            raise HTTPException(
                status_code=500,
                detail=f"模型返回的不是合法 JSON：{result_text[:300]}"
            )

        score_code_understanding = float(parsed.get("score_code_understanding", 0))
        score_concept_mastery = float(parsed.get("score_concept_mastery", 0))
        score_question_response = float(parsed.get("score_question_response", 0))
        total_score = float(parsed.get("total_score", 0))
        grading_reason = str(parsed.get("grading_reason", "")).strip()
        feedback = str(parsed.get("feedback", "")).strip()

        answer = ExperimentAnswer(
            question_id=question.id,
            student_id=student.id,
            answer_text=request.answer_text,
            score_code_understanding=score_code_understanding,
            score_concept_mastery=score_concept_mastery,
            score_question_response=score_question_response,
            total_score=total_score,
            feedback=feedback,
            grading_reason=grading_reason,
        )
        db.add(answer)
        db.commit()
        db.refresh(answer)

        upsert_assignment_score(
            db=db,
            student_id=student.id,
            assignment_no=submission.assignment_no,
            assignment_title=submission.experiment_title,
            score=total_score,
            feedback=feedback,
            graded_by=None,
        )

        submission.status = "graded"
        db.commit()

        return {
            "success": True,
            "message": "回答提交并评分成功",
            "answer": {
                "id": answer.id,
                "question_id": answer.question_id,
                "student_id": answer.student_id,
                "answer_text": answer.answer_text,
                "score_code_understanding": answer.score_code_understanding,
                "score_concept_mastery": answer.score_concept_mastery,
                "score_question_response": answer.score_question_response,
                "total_score": answer.total_score,
                "feedback": answer.feedback,
                "grading_reason": answer.grading_reason,
                "created_at": answer.created_at,
            },
            "assignment_score_written": True,
            "assignment_no": submission.assignment_no,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自动评分失败：{str(e)}")
    
@router.get("/submission-detail/{submission_id}")
async def get_submission_detail(submission_id: int, db: Session = Depends(get_db)):
    submission = (
        db.query(ExperimentSubmission)
        .filter(ExperimentSubmission.id == submission_id)
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="实验报告提交记录不存在")

    questions = (
        db.query(ExperimentQuestion)
        .filter(ExperimentQuestion.submission_id == submission_id)
        .order_by(ExperimentQuestion.question_no.asc())
        .all()
    )

    result = []
    for q in questions:
        answers = (
            db.query(ExperimentAnswer)
            .filter(ExperimentAnswer.question_id == q.id)
            .order_by(ExperimentAnswer.created_at.desc())
            .all()
        )

        result.append({
            "question_id": q.id,
            "question_no": q.question_no,
            "question_text": q.question_text,
            "reference_points": q.reference_points,
            "answers": [
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
                for a in answers
            ],
        })

    return {
        "submission": {
            "id": submission.id,
            "assignment_no": submission.assignment_no,
            "experiment_title": submission.experiment_title,
            "status": submission.status,
            "question_started_at": submission.question_started_at,
            "answer_deadline_at": submission.answer_deadline_at,
        },
        "questions": result,
    }