"""모든 모델 연결 모듈이 따르는 공통 인터페이스와 오류 종류."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    input_tokens: int
    output_tokens: int


class ProviderFailure(Exception):
    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class RateLimited(ProviderFailure):
    """일시적 속도 제한. retry_after 초 뒤 다시 시도할 수 있다."""

    def __init__(self, message: str = "", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class DailyQuotaExhausted(ProviderFailure):
    """일일 한도 소진. reset_at(naive UTC)에 다시 쓸 수 있다."""

    def __init__(self, message: str = "", reset_at: datetime | None = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class CreditsExhausted(ProviderFailure):
    """체험 크레딧 소진. 자동으로 풀리지 않는다."""


class ProviderError(ProviderFailure):
    """네트워크 오류, 서버 오류, 시간 초과, 해석할 수 없는 응답."""


class Provider(Protocol):
    name: str
    model: str

    async def complete(
        self, messages: list[ChatMessage], response_schema: dict | None = None
    ) -> ProviderResponse: ...
