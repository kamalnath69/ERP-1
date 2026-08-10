"""SQLAlchemy engine and session management."""
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

def database_connect_args() -> dict:
    url = make_url(settings.DATABASE_URL)
    if not url.drivername.startswith("postgresql"):
        return {}
    return {
        "connect_timeout": settings.DATABASE_CONNECT_TIMEOUT_SECONDS,
        "application_name": settings.DATABASE_APPLICATION_NAME,
    }


engine = create_engine(
    settings.DATABASE_URL,
    connect_args=database_connect_args(),
    pool_pre_ping=True,
    pool_use_lifo=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
    pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
