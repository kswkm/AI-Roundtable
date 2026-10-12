import json

from pydantic import BaseModel

from roundtable.debate.schemas import Critique, FinalResult, JudgeEval, Opinion, ReviewedOpinion
from roundtable.providers.base import ChatMessage

LANGUAGE_RULE = "질문에 쓰인 언어로 답하세요."
PARTICIPANT_SYSTEM = (
    "당신은 여러 AI가 함께하는 토론의 참여자입니다. 근거를 갖춰 정직하게 판단하세요. "
    "더 나은 논거를 만나면 입장을 바꾸되, 근거 없이 다수 의견에 동조하지 마세요. " + LANGUAGE_RULE
)
JUDGE_SYSTEM = (
    "당신은 여러 AI의 토론을 평가하는 판정자입니다. 다수결이 아니라 근거의 타당성으로 판단하세요. "
    "실제로 합의되지 않았다면 합의되었다고 쓰지 마세요. " + LANGUAGE_RULE
)


def json_instruction(model_cls: type[BaseModel]) -> str:
    schema = json.dumps(model_cls.model_json_schema(), ensure_ascii=False)
    return f"다른 텍스트 없이, 다음 JSON Schema를 따르는 JSON 객체 하나만 출력하세요.\n{schema}"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "(없음)"


def format_opinion(opinion: Opinion) -> str:
    return (
        f"입장: {opinion.position}\n"
        f"근거:\n{_bullets(opinion.reasons)}\n"
        f"전제 조건·한계:\n{_bullets(opinion.conditions)}\n"
        f"확신도: {opinion.confidence:.2f}"
    )


def _labeled(opinions: dict[str, Opinion]) -> str:
    return "\n\n".join(f"[참여자 {label}]\n{format_opinion(op)}" for label, op in opinions.items())


def _participant(user_text: str) -> list[ChatMessage]:
    return [ChatMessage("system", PARTICIPANT_SYSTEM), ChatMessage("user", user_text)]


def _judge(user_text: str) -> list[ChatMessage]:
    return [ChatMessage("system", JUDGE_SYSTEM), ChatMessage("user", user_text)]


def opinion_messages(question: str) -> list[ChatMessage]:
    return _participant(
        f"질문:\n{question}\n\n"
        "다른 참여자의 의견을 보기 전에 당신의 독립적인 의견을 제시하세요.\n\n"
        + json_instruction(Opinion)
    )


def review_messages(
    question: str, own: Opinion, others: dict[str, Opinion], issues: list[str]
) -> list[ChatMessage]:
    sections = [f"질문:\n{question}", f"당신의 직전 의견:\n{format_opinion(own)}"]
    if others:
        sections.append(f"다른 참여자들의 의견:\n{_labeled(others)}")
    sections.append(f"검토할 쟁점과 반론:\n{_bullets(issues)}")
    sections.append(
        "위 내용을 검토해 입장을 수정하거나 유지하세요. changes에는 무엇을 왜 바꿨는지, "
        "또는 왜 유지했는지 쓰고, rebuttals에는 다른 의견에 대한 반박이나 보완을 쓰세요.\n\n"
        + json_instruction(ReviewedOpinion)
    )
    return _participant("\n\n".join(sections))


def judge_eval_messages(
    question: str, opinions: dict[str, Opinion], previous: dict[str, Opinion] | None
) -> list[ChatMessage]:
    sections = [f"질문:\n{question}", f"이번 라운드 의견:\n{_labeled(opinions)}"]
    if previous:
        sections.append(f"직전 라운드 의견:\n{_labeled(previous)}")
    no_previous_rule = "" if previous else " 직전 라운드 의견이 없으므로 stalled를 쓰지 마세요."
    sections.append(
        "토론 상태를 평가하세요.\n"
        "- converged: 모든 참여자가 받아들일 수 있는 하나의 의견이 나왔습니다. 조건부 동의도 포함합니다.\n"
        f"- stalled: 직전 라운드와 비교해 입장 변화도 새로운 논거도 없습니다.{no_previous_rule}\n"
        "- progressing: 그 외의 경우입니다.\n"
        "issues에는 의견이 갈리는 지점과 근거가 약한 지점을, draft에는 지금까지의 통합안 초안을 쓰세요.\n\n"
        + json_instruction(JudgeEval)
    )
    return _judge("\n\n".join(sections))


def critique_messages(question: str, opinion: Opinion) -> list[ChatMessage]:
    return _judge(
        f"질문:\n{question}\n\n참여자의 의견:\n{format_opinion(opinion)}\n\n"
        "이 의견의 약점(weaknesses)과 가능한 반론(counterarguments)을 제시하세요. "
        "참여자가 의견을 개선할 수 있도록 구체적으로 쓰세요.\n\n"
        + json_instruction(Critique)
    )


def final_messages(
    question: str,
    opinions: dict[str, Opinion],
    last_eval: JudgeEval | None,
    end_reason: str,
) -> list[ChatMessage]:
    sections = [f"질문:\n{question}", f"참여자들의 최종 의견:\n{_labeled(opinions)}"]
    if last_eval is not None:
        sections.append(
            f"마지막 판정 쟁점:\n{_bullets(last_eval.issues)}\n"
            f"마지막 통합안 초안:\n{last_eval.draft or '(없음)'}"
        )
    sections.append(
        f"토론 종료 사유: {end_reason}\n\n"
        "토론 결과를 하나의 통합된 최선의 의견(final_opinion)으로 정리하세요. "
        "grade는 consensus(합의), partial(조건부·부분 합의), no_consensus(미합의) 중 실제 상태를 고르세요. "
        "key_reasons에는 핵심 근거를, dissents에는 동의하지 않는 참여자(label)와 그 이유를, "
        "uncertainties에는 확인되지 않은 사실과 전제 조건을 쓰세요.\n\n"
        + json_instruction(FinalResult)
    )
    return _judge("\n\n".join(sections))
