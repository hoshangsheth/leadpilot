from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import config

engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    import models  # noqa: F401 — ensures models are registered before create_all
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
