from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings

class Base(DeclarativeBase):
    pass

@lru_cache
def engine():
    url = get_settings().database_url
    args = {'check_same_thread': False} if url.startswith('sqlite:') else {}
    return create_engine(url, pool_pre_ping=True, connect_args=args)

@lru_cache
def SessionLocal():
    return sessionmaker(bind=engine(), autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()()
    try:
        yield db
    finally:
        db.close()
