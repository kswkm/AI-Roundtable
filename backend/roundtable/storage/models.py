from datetime import datetime

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from roundtable.clock import utcnow


class Slot(SQLModel, table=True):
    id: int = Field(primary_key=True)  # 1~4 참여, 5 판정
    kind: str  # "participant" | "judge"
    provider: str
    model: str
    api_key_env: str
    status: str = "available"  # "available" | "rate_limited" | "exhausted"
    status_until: datetime | None = Field(default=None, sa_type=DateTime())
    status_reason: str | None = None
    known_limit: dict | None = Field(default=None, sa_column=Column(JSON))


class Debate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str | None = None  # 공개 서비스 확장용
    question: str
    # "running" | "paused" | "converged" | "stalled" | "stopped" | "interrupted"
    status: str = "running"
    grade: str | None = None  # "consensus" | "partial" | "no_consensus"
    result: dict | None = Field(default=None, sa_column=Column(JSON))
    participants: list = Field(default_factory=list, sa_column=Column(JSON))
    dropouts: list = Field(default_factory=list, sa_column=Column(JSON))
    stall_threshold: int = 2
    pending_status: str | None = None
    pause_reason: str | None = None
    started_at: datetime = Field(default_factory=utcnow, sa_type=DateTime())
    ended_at: datetime | None = Field(default=None, sa_type=DateTime())


class Round(SQLModel, table=True):
    __tablename__ = "debate_round"

    id: int | None = Field(default=None, primary_key=True)
    debate_id: int = Field(foreign_key="debate.id", index=True)
    number: int
    judge_eval: dict | None = Field(default=None, sa_column=Column(JSON))
    completed_at: datetime | None = Field(default=None, sa_type=DateTime())


class Message(SQLModel, table=True):
    __tablename__ = "debate_message"

    id: int | None = Field(default=None, primary_key=True)
    round_id: int = Field(foreign_key="debate_round.id", index=True)
    label: str
    provider: str
    model: str
    content: dict | None = Field(default=None, sa_column=Column(JSON))
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    error: str | None = None


class UsageLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    model: str
    debate_id: int | None = None
    called_at: datetime = Field(default_factory=utcnow, index=True, sa_type=DateTime())
    input_tokens: int = 0
    output_tokens: int = 0
    outcome: str  # "ok" | "rate_limited" | "quota" | "credits" | "error"


class AppConfig(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
