import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# PUBLIC_INTERFACE
def get_postgres_url():
    """Get the async PostgreSQL database URL from environment variables."""
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

DATABASE_URL = get_postgres_url()

# Async SQLAlchemy setup
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# PUBLIC_INTERFACE
async def get_db():
    """Async session generator for FastAPI route dependencies."""
    async with SessionLocal() as session:
        yield session
