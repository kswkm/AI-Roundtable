from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine

from roundtable.storage import models  # noqa: F401  테이블 등록


def make_engine(url: str) -> Engine:
    return create_engine(url, connect_args={"check_same_thread": False})


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
