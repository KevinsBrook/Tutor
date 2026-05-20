from src.api.routers.assignment_review import (
    ScoringCriterion,
    _ensure_criteria_coverage,
    _extract_question_blocks,
    _fallback_scoring_criteria,
)


def test_extract_question_blocks_with_sections_and_scores():
    text = """
    网络作业
    总分：100 分
    一、小题（共 40 分，每题 4 分）
    1. 选择题：传输层提供什么服务？
    2. 填空题：UDP 首部长度为 ____ 字节。
    3. 判断题：TCP 只关心接收端缓存。（ ）
    4. 简答题：说明端口号的作用。
    5. 计算题：cwnd = 16 MSS，经过 3 个 RTT 后是多少？
    6. 填空题：SYN 表示 ____。
    7. 简答题：TCP 如何进行流量控制？
    8. 判断题：UDP 一定不能用于实时业务。（ ）
    9. 简答题：比较 UDP 和 TCP。
    10. 计算题：慢启动阶段 cwnd 如何增长？
    二、大题（共 60 分）
    1. 可靠传输机制分析（15 分）
    请回答：接收方如何确认？发送方如何重传？选择确认有什么不同？
    2. TCP 三次握手与四次挥手（15 分）
    请说明三次握手过程，以及 TIME_WAIT 的作用。
    3. TCP 拥塞控制计算（15 分）
    请给出 cwnd 与 ssthresh 的变化。
    4. 应用场景设计题（15 分）
    请分别判断直播、下载、测验和聊天适合 UDP 还是 TCP。
    评分参考
    基础概念 25
    """

    blocks = _extract_question_blocks("", text, [])

    assert [block["question_no"] for block in blocks] == [
        "一.1",
        "一.2",
        "一.3",
        "一.4",
        "一.5",
        "一.6",
        "一.7",
        "一.8",
        "一.9",
        "一.10",
        "二.1",
        "二.2",
        "二.3",
        "二.4",
    ]
    assert sum(float(block["score"]) for block in blocks) == 100
    assert blocks[0]["score"] == 4
    assert blocks[-1]["score"] == 15
    assert "评分参考" not in blocks[-1]["text"]


def test_fallback_criteria_cover_all_questions_and_keep_total_score():
    text = """
    一、小题（共 8 分，每题 4 分）
    1. 选择题：传输层核心服务是？
    2. 简答题：为什么 TCP 需要流量控制？它通过什么字段实现？
    二、大题（共 12 分）
    1. 可靠传输机制分析（12 分）
    请回答：接收方如何确认？发送方如何发现丢包？选择确认有什么不同？
    """

    criteria = _fallback_scoring_criteria(title="", description=text, expected_total_score=20)
    question_nos = {item.question_no for item in criteria}

    assert {"一.1", "一.2", "二.1"}.issubset(question_nos)
    assert round(sum(item.score for item in criteria), 2) == 20


def test_incomplete_llm_criteria_are_replaced_by_structured_coverage():
    text = """
    一、小题（共 8 分，每题 4 分）
    1. 选择题：传输层核心服务是？
    2. 填空题：UDP 首部长度是多少？
    二、大题（共 12 分）
    1. 可靠传输机制分析（12 分）
    请回答：接收方如何确认？发送方如何重传？
    """
    blocks = _extract_question_blocks("", text, [])
    bad_llm_items = [
        ScoringCriterion(question_no="1", criterion="只覆盖了第一题", score=4),
        ScoringCriterion(question_no="2", criterion="只覆盖了第二题", score=4),
    ]

    covered = _ensure_criteria_coverage(bad_llm_items, blocks, 20)

    assert {item.question_no for item in covered} == {"一.1", "一.2", "二.1"}
    assert round(sum(item.score for item in covered), 2) == 20
