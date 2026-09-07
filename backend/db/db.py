"""Database engine/session setup (SQLAlchemy, Postgres via Supabase) and schema init."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import config

engine = create_engine(
    config.DATABASE_URL,
    # pool_pre_ping tests every pooled connection with a cheap SELECT 1 before handing it
    # out. Without it, a connection Supabase's pooler silently dropped while idle gets reused
    # anyway, and the first real query on it hangs until the OS-level TCP timeout instead of
    # failing fast — this is exactly what produced a "could not send data to server:
    # Connection timed out" on 2026-09-07, which meant no reply was sent for a real inbound
    # message and nobody was told. pool_recycle forces a periodic refresh so connections don't
    # sit idle long enough to be dropped in the first place; connect_timeout bounds how long a
    # genuinely dead server takes to fail instead of hanging indefinitely.
    pool_pre_ping=True,
    pool_recycle=280,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    from db import models  # noqa: F401 — ensures models are registered before create_all
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
