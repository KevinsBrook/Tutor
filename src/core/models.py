from datetime import datetime

from sqlalchemy import (
    Boolean,
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
    uploaded_materials = relationship("CourseMaterial", back_populates="student_uploader")
    mastery_records = relationship("StudentKnowledgeMastery", back_populates="student")
    mastery_events = relationship("KnowledgeMasteryEvent", back_populates="student")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    real_name = Column(String(50), nullable=False)
    teacher_no = Column(String(50), unique=True, nullable=True, index=True)
    department = Column(String(100), nullable=True)

    user = relationship("User", back_populates="teacher")
    graded_scores = relationship("AssignmentScore", back_populates="grader")
    courses = relationship("Course", back_populates="teacher")
    created_knowledge_points = relationship("KnowledgePoint", back_populates="creator_teacher")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("teacher_id", "name", name="uq_teacher_course_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(30), default="active", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    teacher = relationship("Teacher", back_populates="courses")
    chapters = relationship(
        "CourseChapter",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseChapter.order_index",
    )
    materials = relationship("CourseMaterial", back_populates="course")
    knowledge_points = relationship("KnowledgePoint", back_populates="course")


class CourseChapter(Base):
    __tablename__ = "course_chapters"
    __table_args__ = (
        UniqueConstraint("course_id", "order_index", name="uq_course_chapter_order"),
        UniqueConstraint("course_id", "title", name="uq_course_chapter_title"),
    )

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, default=1, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    course = relationship("Course", back_populates="chapters")
    materials = relationship("CourseMaterial", back_populates="chapter")
    knowledge_points = relationship("KnowledgePoint", back_populates="chapter")


class CourseMaterial(Base):
    __tablename__ = "course_materials"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    chapter_id = Column(Integer, ForeignKey("course_chapters.id"), nullable=True, index=True)
    uploader_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    student_uploader_id = Column(Integer, ForeignKey("students.id"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    source_type = Column(String(40), nullable=False, index=True)
    original_filename = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=True)
    file_type = Column(String(50), nullable=True)
    kb_name = Column(String(200), nullable=True, index=True)
    rag_provider = Column(String(80), nullable=True)
    parse_status = Column(String(40), default="pending", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    course = relationship("Course", back_populates="materials")
    chapter = relationship("CourseChapter", back_populates="materials")
    uploader = relationship("User")
    student_uploader = relationship("Student", back_populates="uploaded_materials")
    knowledge_points = relationship("KnowledgePoint", back_populates="source_material")


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"
    __table_args__ = (
        UniqueConstraint("course_id", "chapter_id", "name", name="uq_course_chapter_kp_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    chapter_id = Column(Integer, ForeignKey("course_chapters.id"), nullable=True, index=True)
    source_material_id = Column(Integer, ForeignKey("course_materials.id"), nullable=True, index=True)
    created_by_teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    priority = Column(Integer, default=3, nullable=False, index=True)
    source_type = Column(String(40), default="teacher_material", nullable=False, index=True)
    source_ref = Column(Text, nullable=True)
    is_confirmed = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    course = relationship("Course", back_populates="knowledge_points")
    chapter = relationship("CourseChapter", back_populates="knowledge_points")
    source_material = relationship("CourseMaterial", back_populates="knowledge_points")
    creator_teacher = relationship("Teacher", back_populates="created_knowledge_points")
    mastery_records = relationship("StudentKnowledgeMastery", back_populates="knowledge_point")
    mastery_events = relationship("KnowledgeMasteryEvent", back_populates="knowledge_point")


class StudentKnowledgeMastery(Base):
    __tablename__ = "student_knowledge_mastery"
    __table_args__ = (
        UniqueConstraint("student_id", "knowledge_point_id", name="uq_student_knowledge_point"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=False, index=True)
    mastery_level = Column(Float, default=0.0, nullable=False, index=True)
    correct_count = Column(Integer, default=0, nullable=False)
    wrong_count = Column(Integer, default=0, nullable=False)
    practice_count = Column(Integer, default=0, nullable=False)
    last_practiced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    student = relationship("Student", back_populates="mastery_records")
    knowledge_point = relationship("KnowledgePoint", back_populates="mastery_records")


class KnowledgeMasteryEvent(Base):
    __tablename__ = "knowledge_mastery_events"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=False, index=True)
    source_type = Column(String(40), nullable=False, index=True)
    source_id = Column(String(80), nullable=True, index=True)
    score = Column(Float, nullable=True)
    max_score = Column(Float, nullable=True)
    is_correct = Column(Boolean, nullable=True, index=True)
    mastery_delta = Column(Float, default=0.0, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    student = relationship("Student", back_populates="mastery_events")
    knowledge_point = relationship("KnowledgePoint", back_populates="mastery_events")


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
    question_started_at = Column(DateTime, nullable=True)
    answer_deadline_at = Column(DateTime, nullable=True)
    assignment_no = Column(Integer, nullable=False, index=True)  # 第几次实验
    experiment_title = Column(String(200), nullable=False)
    question_started_at = Column(DateTime, nullable=True)
    answer_deadline_at = Column(DateTime, nullable=True)
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
    # 语音作答过程性评价指标
    # pause_count：学生回答过程中的明显停顿次数
    # longest_pause_ms：最长一次停顿时间，单位毫秒
    # answer_duration_seconds：本题总回答时长，单位秒
    pause_count = Column(Integer, default=0, nullable=False)
    longest_pause_ms = Column(Integer, default=0, nullable=False)
    answer_duration_seconds = Column(Integer, nullable=True)

    score_code_understanding = Column(Float, nullable=True)   # 代码理解 2 分
    score_concept_mastery = Column(Float, nullable=True)      # 概念掌握 1 分
    score_question_response = Column(Float, nullable=True)    # 问题回答 2 分
    total_score = Column(Float, nullable=True)                # 总分 5 分

    feedback = Column(Text, nullable=True)
    grading_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    question = relationship("ExperimentQuestion")
    student = relationship("Student")
