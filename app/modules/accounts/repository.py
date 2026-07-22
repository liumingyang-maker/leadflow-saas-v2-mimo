from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from flask import Flask
from sqlalchemy.orm import Session

from app.extensions import get_engine


@contextmanager
def session_scope(app: Flask) -> Iterator[Session]:
    session = Session(get_engine(app))
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
