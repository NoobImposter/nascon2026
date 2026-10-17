import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL

log = logging.getLogger("nascon.db")

# 2 workers x (20+10) = 60 connections max, under Postgres' default of 100.
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=10, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001
            if time.time() > deadline:
                raise
            log.warning("database not ready yet: %s", exc)
            time.sleep(1.5)
