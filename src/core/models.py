from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from src.core.database import Base
from sqlalchemy import Boolean


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, index=True)  # teacher / student
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    student = relationship("Student", back_populates="user", uselist=False)
    teacher = relationship("Teacher", back_populates="user", uselist=False)


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    real_name = Column(String(50), nullable=False)
    student_no = Column(String(50), unique=True, nullable=False, index=True)
    grade_name = Column(String(50), nullable=False)   # 例如 2023级
    class_name = Column(String(50), nullable=False)   # 例如 计科1班
    major = Column(String(100), nullable=True)

    user = relationship("User", back_populates="student")
    scores = relationship("AssignmentScore", back_populates="student")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    real_name = Column(String(50), nullable=False)
    teacher_no = Column(String(50), unique=True, nullable=True, index=True)
    department = Column(String(100), nullable=True)

    user = relationship("User", back_populates="teacher")
    graded_scores = relationship("AssignmentScore", back_populates="grader")


class AssignmentScore(Base):
    __tablename__ = "assignment_scores"
    __table_args__ = (
        UniqueConstraint("student_id", "assignment_no", name="uq_student_assignment_no"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)

    assignment_no = Column(Integer, nullable=False, index=True)  # 第几次作业
    assignment_title = Column(String(200), nullable=True)
    score = Column(Float, nullable=False)
    feedback = Column(Text, nullable=True)

    graded_by = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    graded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student = relationship("Student", back_populates="scores")
    grader = relationship("Teacher", back_populates="graded_scores")

class ExperimentSubmission(Base):
    __tablename__ = "experiment_submissions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)

    assignment_no = Column(Integer, nullable=False, index=True)  # 第几次实验
    experiment_title = Column(String(200), nullable=False)

    original_filename = Column(String(255), nullable=False)
    report_file_path = Column(String(500), nullable=False)
    report_text = Column(Text, nullable=True)

    status = Column(String(50), default="uploaded", nullable=False)  # uploaded / parsed / questioned / graded
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student = relationship("Student")
class ExperimentQuestion(Base):
    __tablename__ = "experiment_questions"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("experiment_submissions.id"), nullable=False, index=True)

    question_no = Column(Integer, nullable=False)   # 第几题
    question_text = Column(Text, nullable=False)
    reference_points = Column(Text, nullable=True)  # 可先存参考要点，后面评分用
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    submission = relationship("ExperimentSubmission")

class ExperimentAnswer(Base):
    __tablename__ = "experiment_answers"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("experiment_questions.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)

    answer_text = Column(Text, nullable=False)

    score_code_understanding = Column(Float, nullable=True)   # 代码理解 2 分
    score_concept_mastery = Column(Float, nullable=True)      # 概念掌握 1 分
    score_question_response = Column(Float, nullable=True)    # 问题回答 2 分
    total_score = Column(Float, nullable=True)                # 总分 5 分

    feedback = Column(Text, nullable=True)
    grading_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    question = relationship("ExperimentQuestion")
    student = relationship("Student")