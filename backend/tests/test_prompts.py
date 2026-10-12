from roundtable.debate import prompts
from roundtable.debate.schemas import JudgeEval, Opinion

A = Opinion(position="POS-A", reasons=["근거-A"], confidence=0.7)
B = Opinion(position="POS-B", reasons=["근거-B"], conditions=["조건-B"], confidence=0.6)


def text(messages):
    return "\n".join(m.content for m in messages)


def test_opinion_messages_contain_only_question():
    messages = prompts.opinion_messages("자동 배포해도 되는가?")
    assert [m.role for m in messages] == ["system", "user"]
    body = text(messages)
    assert "자동 배포해도 되는가?" in body
    assert "독립적인 의견" in body
    assert "JSON" in body
    assert "[참여자" not in body


def test_review_messages_show_others_by_label_and_issues():
    body = text(prompts.review_messages("Q", A, {"B": B}, ["쟁점-1"]))
    assert "POS-A" in body  # 자기 직전 의견
    assert "[참여자 B]" in body and "POS-B" in body and "조건-B" in body
    assert "쟁점-1" in body
    assert "changes" in body


def test_review_messages_without_others_is_single_mode():
    body = text(prompts.review_messages("Q", A, {}, ["약점-1"]))
    assert "[참여자" not in body
    assert "약점-1" in body


def test_judge_eval_messages_forbid_stalled_without_previous():
    first = text(prompts.judge_eval_messages("Q", {"A": A, "B": B}, None))
    later = text(prompts.judge_eval_messages("Q", {"A": A}, {"A": B}))
    assert "stalled를 쓰지 마세요" in first
    assert "stalled를 쓰지 마세요" not in later
    assert "직전 라운드 의견" in later
    assert prompts.JUDGE_SYSTEM == prompts.judge_eval_messages("Q", {"A": A}, None)[0].content


def test_critique_and_final_messages():
    assert "weaknesses" in text(prompts.critique_messages("Q", A))
    final = text(prompts.final_messages("Q", {"A": A}, JudgeEval(status="stalled", issues=["남은 쟁점"], draft="초안-X"), "정체"))
    assert "토론 종료 사유: 정체" in final
    assert "남은 쟁점" in final and "초안-X" in final
    assert "no_consensus" in final
