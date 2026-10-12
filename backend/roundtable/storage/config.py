from sqlalchemy import Engine
from sqlmodel import Session

from roundtable.storage.models import AppConfig

STALL_THRESHOLD_KEY = "stall_threshold"
DEFAULT_STALL_THRESHOLD = 2


class ConfigStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def stall_threshold(self) -> int:
        with Session(self._engine) as session:
            row = session.get(AppConfig, STALL_THRESHOLD_KEY)
            return int(row.value) if row is not None else DEFAULT_STALL_THRESHOLD

    def set_stall_threshold(self, value: int) -> None:
        with Session(self._engine) as session:
            row = session.get(AppConfig, STALL_THRESHOLD_KEY) or AppConfig(key=STALL_THRESHOLD_KEY, value="")
            row.value = str(value)
            session.add(row)
            session.commit()
