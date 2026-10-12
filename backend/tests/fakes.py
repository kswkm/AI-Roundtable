import json

from roundtable.providers.base import ChatMessage, ProviderResponse

ALL_KEYS = {
    "OPENAI_API_KEY": "k",
    "ANTHROPIC_API_KEY": "k",
    "GEMINI_API_KEY": "k",
    "XAI_API_KEY": "k",
}


async def no_sleep(_seconds: float) -> None:
    return None


class ScriptedProvider:
    """미리 정한 대본대로 응답하거나 오류를 내는 가짜 Provider. 실제 API를 호출하지 않는다."""

    def __init__(self, script, name: str = "fake", model: str = "fake-model") -> None:
        self.name = name
        self.model = model
        self.script = list(script)
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages, response_schema=None) -> ProviderResponse:
        self.calls.append(list(messages))
        if not self.script:
            raise AssertionError(f"{self.name}: 대본이 끝났는데 호출됨")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        text = item(messages) if callable(item) else item
        return ProviderResponse(text, 10, 5)

    def prompt(self, index: int) -> str:
        return "\n".join(m.content for m in self.calls[index])


def op_json(position: str, *, confidence: float = 0.7) -> str:
    return json.dumps(
        {"position": position, "reasons": [f"{position}의 근거"], "conditions": [], "confidence": confidence},
        ensure_ascii=False,
    )


def review_json(position: str, changes: str = "유지") -> str:
    data = json.loads(op_json(position))
    data |= {"changes": changes, "rebuttals": []}
    return json.dumps(data, ensure_ascii=False)


def eval_json(status: str, issues=(), draft: str = "초안") -> str:
    return json.dumps({"status": status, "issues": list(issues), "draft": draft}, ensure_ascii=False)


def critique_json(weaknesses=("약점-1",), counterarguments=("반론-1",)) -> str:
    return json.dumps(
        {"weaknesses": list(weaknesses), "counterarguments": list(counterarguments)}, ensure_ascii=False
    )


def final_json(grade: str = "consensus", final_opinion: str = "통합 의견") -> str:
    return json.dumps(
        {"final_opinion": final_opinion, "grade": grade, "key_reasons": ["핵심 근거"],
         "dissents": [], "uncertainties": ["불확실성"]},
        ensure_ascii=False,
    )
