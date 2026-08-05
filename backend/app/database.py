from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={
        # Safety net: have Postgres kill transactions that sit idle for 5
        # minutes, so one leaked session can't wedge the whole pool.
        # pool_pre_ping recycles the killed connections on next checkout.
        "options": "-c idle_in_transaction_session_timeout=300000",
    },
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
