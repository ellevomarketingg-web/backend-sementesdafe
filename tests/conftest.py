import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator
import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Configure test environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["STORAGE_PATH"] = "./tests/temp_storage"

from app.models.base import Base
from app.core.database import get_db
from app.core.config import settings
from app.main import app
from app.services.communication_service import CommunicationService
from app.services.evolution_service import evolution_service


# Test database engine
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    """Cria e recria as tabelas do banco antes de cada teste."""
    os.makedirs(settings.STORAGE_PATH, exist_ok=True)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Garante templates padrão
    async with TestSessionLocal() as session:
        await CommunicationService.ensure_default_templates(session)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def admin_headers() -> dict:
    return {"X-Admin-API-Key": settings.ADMIN_API_KEY}


@pytest.fixture(autouse=True)
def mock_evolution_api(monkeypatch):
    """Mock do serviço da Evolution API para envio sem rede real."""
    async def mock_send_text(phone: str, message: str):
        return {
            "success": True,
            "external_message_id": f"mock_msg_{phone}_12345",
            "data": {"status": "PENDING"},
            "error": None,
        }

    async def mock_send_document(phone: str, document_url_or_base64: str, filename: str = "", caption: str = ""):
        return {
            "success": True,
            "external_message_id": f"mock_doc_{phone}_67890",
            "data": {"status": "PENDING"},
            "error": None,
        }

    monkeypatch.setattr(evolution_service, "send_text", mock_send_text)
    monkeypatch.setattr(evolution_service, "send_document", mock_send_document)
