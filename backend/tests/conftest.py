from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database, models


@pytest.fixture
def session(tmp_path):
    db_file = tmp_path / "pgl.sqlite3"
    database_url = f"sqlite:///{Path(db_file).as_posix()}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    database.engine = engine
    database.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    models.Base.metadata.create_all(bind=engine)
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()
        models.Base.metadata.drop_all(bind=engine)
        engine.dispose()
