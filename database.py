import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Use Vercel Postgres URL if available, otherwise use local SQLite for development
if os.getenv("POSTGRES_URL"):
    # Vercel Postgres
    SQLALCHEMY_DATABASE_URL = os.getenv("POSTGRES_URL").replace("postgres://", "postgresql://")
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
else:
    # Local SQLite for development
    SQLALCHEMY_DATABASE_URL = "sqlite:///./brainbuzz.db"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
