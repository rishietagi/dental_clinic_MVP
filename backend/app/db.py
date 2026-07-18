"""Database engine, session factory, and the FastAPI session dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# The engine holds a pool of connections to Postgres.
# pool_pre_ping tests a pooled connection with a cheap query before handing it
# out, so a connection the server has silently dropped (idle timeout, restart)
# is replaced instead of failing a request. Worth it on flaky clinic internet.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# A session is one unit of work (one transaction). SessionLocal makes them.
# expire_on_commit=False keeps loaded objects usable after commit instead of
# forcing a re-query on next access.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a session and always close it afterwards.

    Usage in a route:  db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
