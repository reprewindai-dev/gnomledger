from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()


def create_engine_from_settings() -> "Engine":
    connect_args: dict[str, bool] = {}
    if settings.database_url.startswith("sqlite"):
        sqlite_path = settings.database_url.removeprefix("sqlite:///")
        if sqlite_path and sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


class Base(DeclarativeBase):
    pass


engine = create_engine_from_settings()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def ensure_schema() -> None:
    from . import models  # imported lazily so model metadata is registered

    Base.metadata.create_all(bind=engine)


def init_database() -> None:
    ensure_schema()


def reset_database_for_tests() -> None:
    Base.metadata.drop_all(bind=engine)
    init_database()


@contextmanager
def db_session() -> Generator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
