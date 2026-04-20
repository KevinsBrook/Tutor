from src.api.utils.assignment_review_repository import JsonAssignmentReviewRepository


def test_json_assignment_review_repository_roundtrip(tmp_path):
    repo = JsonAssignmentReviewRepository()
    path = tmp_path / "sample.json"
    payload = {"items": [{"id": "x1", "v": 1}]}

    repo.init_json_file(path, {"items": []})
    repo.write_json(path, payload)
    data = repo.read_json(path)

    assert data == payload
