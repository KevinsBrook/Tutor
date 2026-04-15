from src.api.utils.assignment_review_store import AssignmentReviewStore
from src.api.utils.assignment_review_repository import JsonAssignmentReviewRepository


def test_assignment_review_store_flow(tmp_path):
    store = AssignmentReviewStore(root_dir=tmp_path, repository=JsonAssignmentReviewRepository())

    assignment = store.create_assignment(
        teacher_username="teacher",
        title="实验一",
        description="完成线性回归实验",
        rubric_items=[{"name": "准确性", "score": 100}],
        files=[],
    )
    assert assignment["status"] == "draft"

    published = store.confirm_assignment(assignment["id"], "teacher")
    assert published is not None
    assert published["confirmed"] is True

    submission = store.create_submission(
        student_username="student",
        assignment_id=assignment["id"],
        answer_text="这是我的实验报告",
        files=[],
        auto_review={"total_score": 75},
    )
    assert submission["status"] == "submitted"

    reviewed = store.review_submission(
        submission_id=submission["id"],
        teacher_username="teacher",
        total_score=58,
        feedback="有改进空间",
        rubric_scores=[{"name": "准确性", "score": 58, "max_score": 100, "comment": "偏低"}],
        wrongbook_items=[],
    )
    assert reviewed is not None
    assert reviewed["status"] == "reviewed"

    wrong_items = store.list_wrongbook_items("student")
    assert len(wrong_items) >= 1

    appended = store.append_wrongbook_practice(
        student_username="student",
        item_id=wrong_items[0]["id"],
        practice={"id": "p1", "prompt": "再练一次"},
    )
    assert appended is not None
    assert len(appended.get("practice_history", [])) == 1
