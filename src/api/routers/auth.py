from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from src.api.utils.auth_utils import hash_password, verify_password
from src.core.database import get_db
from src.core.models import Student, Teacher, User

router = APIRouter()


# =========================
# Request / Response Models
# =========================

class StudentRegisterRequest(BaseModel):
    username: str
    email: EmailStr | None = None
    password: str

    real_name: str
    student_no: str
    grade_name: str
    class_name: str
    major: str | None = None


class TeacherRegisterRequest(BaseModel):
    username: str
    email: EmailStr | None = None
    password: str

    real_name: str
    teacher_no: str | None = None
    department: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfoResponse(BaseModel):
    id: int
    username: str
    email: str | None
    role: Literal["teacher", "student"]


# =========================
# Helper
# =========================

def _get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def _get_user_by_email(db: Session, email: str | None) -> User | None:
    if not email:
        return None
    return db.query(User).filter(User.email == email).first()


# =========================
# Register: Student
# =========================

@router.post("/register/student")
async def register_student(request: StudentRegisterRequest, db: Session = Depends(get_db)):
    # 1. 校验 username / email / student_no 是否重复
    existing_user = _get_user_by_username(db, request.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    if request.email:
        existing_email = _get_user_by_email(db, request.email)
        if existing_email:
            raise HTTPException(status_code=400, detail="邮箱已存在")

    existing_student = (
        db.query(Student)
        .filter(Student.student_no == request.student_no)
        .first()
    )
    if existing_student:
        raise HTTPException(status_code=400, detail="学号已存在")

    # 2. 创建 users
    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
        role="student",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()  # 先拿到 user.id

    # 3. 创建 students
    student = Student(
        user_id=user.id,
        real_name=request.real_name,
        student_no=request.student_no,
        grade_name=request.grade_name,
        class_name=request.class_name,
        major=request.major,
    )
    db.add(student)
    db.commit()
    db.refresh(user)
    db.refresh(student)

    return {
        "success": True,
        "message": "学生注册成功",
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


# =========================
# Register: Teacher
# =========================

@router.post("/register/teacher")
async def register_teacher(request: TeacherRegisterRequest, db: Session = Depends(get_db)):
    # 1. 校验 username / email / teacher_no 是否重复
    existing_user = _get_user_by_username(db, request.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    if request.email:
        existing_email = _get_user_by_email(db, request.email)
        if existing_email:
            raise HTTPException(status_code=400, detail="邮箱已存在")

    if request.teacher_no:
        existing_teacher = (
            db.query(Teacher)
            .filter(Teacher.teacher_no == request.teacher_no)
            .first()
        )
        if existing_teacher:
            raise HTTPException(status_code=400, detail="教师工号已存在")

    # 2. 创建 users
    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
        role="teacher",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()

    # 3. 创建 teachers
    teacher = Teacher(
        user_id=user.id,
        real_name=request.real_name,
        teacher_no=request.teacher_no,
        department=request.department,
    )
    db.add(teacher)
    db.commit()
    db.refresh(user)
    db.refresh(teacher)

    return {
        "success": True,
        "message": "教师注册成功",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        },
        "teacher": {
            "id": teacher.id,
            "real_name": teacher.real_name,
            "teacher_no": teacher.teacher_no,
            "department": teacher.department,
        },
    }


# =========================
# Login
# =========================

@router.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = _get_user_by_username(db, request.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    profile = None
    if user.role == "student":
        student = db.query(Student).filter(Student.user_id == user.id).first()
        if student:
            profile = {
                "real_name": student.real_name,
                "student_no": student.student_no,
                "grade_name": student.grade_name,
                "class_name": student.class_name,
                "major": student.major,
            }
    elif user.role == "teacher":
        teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
        if teacher:
            profile = {
                "real_name": teacher.real_name,
                "teacher_no": teacher.teacher_no,
                "department": teacher.department,
            }

    return {
        "success": True,
        "message": "登录成功",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        },
        "profile": profile,
    }


# =========================
# Me (simple version)
# =========================

@router.get("/me/{username}")
async def get_me(username: str, db: Session = Depends(get_db)):
    user = _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    profile = None
    if user.role == "student":
        student = db.query(Student).filter(Student.user_id == user.id).first()
        if student:
            profile = {
                "real_name": student.real_name,
                "student_no": student.student_no,
                "grade_name": student.grade_name,
                "class_name": student.class_name,
                "major": student.major,
            }
    elif user.role == "teacher":
        teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
        if teacher:
            profile = {
                "real_name": teacher.real_name,
                "teacher_no": teacher.teacher_no,
                "department": teacher.department,
            }

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        },
        "profile": profile,
    }