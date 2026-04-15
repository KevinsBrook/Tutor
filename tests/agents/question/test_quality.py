from src.agents.question.quality import (
    build_question_audit,
    normalize_bloom_level,
    normalize_question_schema,
)


def test_normalize_bloom_level_alias():
    assert normalize_bloom_level("analysis") == "analyze"
    assert normalize_bloom_level("unknown_level") == "understand"


def test_normalize_question_schema_true_false():
    normalized = normalize_question_schema(
        {
            "question_type": "tf",
            "question": "牛顿第一定律适用于惯性系。",
            "correct_answer": "正确",
            "explanation": "惯性定律在惯性参考系成立。",
        },
        requested_type="true_false",
        cognitive_level="remember",
    )
    assert normalized["question_type"] == "true_false"
    assert normalized["options"] == {"A": "正确", "B": "错误"}
    assert normalized["correct_answer"] == "A"
    assert normalized["cognitive_level"] == "remember"


def test_build_question_audit_for_choice():
    question = {
        "question_type": "choice",
        "question": "以下哪一项最能描述过拟合？",
        "options": {
            "A": "泛化能力好",
            "B": "训练误差低但测试误差高",
            "C": "欠拟合",
            "D": "数据增强",
        },
        "correct_answer": "B",
        "distractor_meta": {"candidate_count": 5, "selected_count": 3, "duplicate_removed": 2},
    }
    audit = build_question_audit(
        question=question,
        requested_difficulty="medium",
        relevance="high",
        kb_coverage="覆盖机器学习基础概念",
    )
    assert audit["distractor_quality"] == "acceptable"
    assert audit["answer_uniqueness"] == "likely_unique"
    assert audit["source_count"] == 0
    assert audit["distractor_candidate_count"] == 5
    assert audit["distractor_selected_count"] == 3
    assert audit["distractor_duplicate_removed"] == 2
    assert audit["format_ok"] is True
