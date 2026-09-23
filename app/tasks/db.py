from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Celery workers run synchronously, so tasks use a separate sync engine
# rather than sharing the app's async engine/event loop.
sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True, future=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, expire_on_commit=False)


@contextmanager
def sync_db_session():
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
