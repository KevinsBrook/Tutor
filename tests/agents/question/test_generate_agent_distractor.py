from src.agents.question.agents.generate_agent import GenerateAgent


def _agent_without_init() -> GenerateAgent:
    # We only test pure helper logic; no BaseAgent init needed.
    return object.__new__(GenerateAgent)


def test_refine_choice_question_keeps_unique_distractors():
    agent = _agent_without_init()
    question = {
        "question_type": "choice",
        "question": "下列哪项是二叉搜索树的性质？",
        "options": {
            "A": "左子树节点值都小于根节点",
            "B": "左子树节点值都小于根节点",  # duplicate candidate
            "C": "任意节点有三个子节点",
            "D": "所有叶子节点都有两个子节点",
        },
        "correct_answer": "A",
    }

    refined = agent._refine_choice_question(question)
    options = refined["options"]

    assert len(options) == 4
    assert refined["correct_answer"] in {"A", "B", "C", "D"}
    assert len(set(options.values())) == 4


def test_refine_multiple_choice_question_generates_answer_labels():
    agent = _agent_without_init()
    question = {
        "question_type": "multiple_choice",
        "question": "哪些属于监督学习任务？",
        "options": {
            "A": "分类",
            "B": "回归",
            "C": "聚类",
            "D": "降维",
        },
        "correct_answer": "A,B",
    }

    refined = agent._refine_multiple_choice_question(question)
    labels = [x for x in refined["correct_answer"].split(",") if x]

    assert len(refined["options"]) >= 4
    assert len(labels) >= 1
    assert all(label in refined["options"] for label in labels)
