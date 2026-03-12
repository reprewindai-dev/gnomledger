from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends

from .database import SessionLocal


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def db_dependency() -> Generator:
    return Depends(get_db)
