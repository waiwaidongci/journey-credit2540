from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .settings import DATABASE_URL
class Base(DeclarativeBase):
    pass
connect_args={"check_same_thread":False,"timeout":30} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
def get_db():
    with SessionLocal() as db:
        yield db
