import json

from src.agents.question.repository import JsonQuestionRunRepository


def test_json_repository_write_files(tmp_path):
    repo = JsonQuestionRunRepository()
    batch = tmp_path / "batch_001"
    batch.mkdir(parents=True, exist_ok=True)

    repo.save_knowledge(batch, {"queries": ["q1"], "retrievals": [{"id": "doc1"}]})
    repo.save_plan(
        batch,
        {"knowledge_point": "测试点", "difficulty": "medium", "question_type": "choice", "focuses": []},
    )
    repo.save_question_result(
        batch,
        {"question_id": "q_1", "question": {"question": "test", "correct_answer": "A"}},
    )
    repo.save_summary(batch, {"requested": 1, "completed": 1, "failed": 0})

    assert (batch / "knowledge.json").exists()
    assert (batch / "plan.json").exists()
    assert (batch / "q_1" / "result.json").exists()
    assert (batch / "summary.json").exists()

    with open(batch / "summary.json", encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["completed"] == 1

