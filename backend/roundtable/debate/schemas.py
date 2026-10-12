from typing import Literal, TypeVar

from pydantic import BaseModel, Field, field_validator


class Opinion(BaseModel):
    position: str
    reasons: list[str]
    conditions: list[str] = []
    confidence: float = Field(ge=0, le=1)

    @field_validator("confidence", mode="before")
    @classmethod
    def _percent_to_fraction(cls, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 1 < value <= 100:
            return value / 100
        return value


class ReviewedOpinion(Opinion):
    changes: str
    rebuttals: list[str] = []


class JudgeEval(BaseModel):
    status: Literal["converged", "progressing", "stalled"]
    issues: list[str] = []
    draft: str = ""


class Critique(BaseModel):
    weaknesses: list[str]
    counterarguments: list[str] = []


class Dissent(BaseModel):
    label: str
    reason: str


class FinalResult(BaseModel):
    final_opinion: str
    grade: Literal["consensus", "partial", "no_consensus"]
    key_reasons: list[str]
    dissents: list[Dissent] = []
    uncertainties: list[str] = []


T = TypeVar("T", bound=BaseModel)


def parse_json_model(text: str, model_cls: type[T]) -> T:
    """응답에서 첫 '{'부터 마지막 '}'까지를 JSON으로 읽는다. 코드 펜스나 앞뒤 설명문을 허용한다."""
    if not isinstance(text, str):
        text = str(text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("JSON 객체를 찾을 수 없음")
    return model_cls.model_validate_json(text[start : end + 1])
