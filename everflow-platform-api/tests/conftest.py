"""Pytest fixtures: in-memory SQLite app + HTTP client."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_async_session, init_db
from app.main import create_app
from app.models import (  # noqa: F401
    AgentCollectionGrant,
    AiUsageEvent,
    KnowledgeCanvas,
    KnowledgeCanvasVersion,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeEvalQuestion,
    KnowledgeEvalSet,
    KnowledgeLink,
    KnowledgeMindMap,
    OAuthAccount,
    Organization,
    OrganizationMember,
    Project,
    ProjectAgent,
    ProviderCredential,
    SandboxAccessToken,
    User,
    Workflow,
    WorkflowCredential,
    WorkflowDataTable,
    WorkflowDataTableRow,
    WorkflowRun,
)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        environment="test",
        debug=False,
        secret_key="test-secret-key-for-jwt-signing-not-for-prod",
        database_url="sqlite+aiosqlite:///:memory:",
        cors_origins=["http://localhost:5173"],
        github_client_id="",
        github_client_secret="",
        google_client_id="",
        google_client_secret="",
        sandbox_enabled=False,
        sandbox_agent_url="http://sandbox-agent-test:8090",
        sandbox_agent_token="test-agent-token",
    )


@pytest_asyncio.fixture
async def client(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SECRET_KEY", test_settings.secret_key)
    monkeypatch.setenv("DATABASE_URL", test_settings.database_url)
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SANDBOX_ENABLED", "false")
    monkeypatch.setenv("SANDBOX_AGENT_URL", test_settings.sandbox_agent_url)
    monkeypatch.setenv("SANDBOX_AGENT_TOKEN", test_settings.sandbox_agent_token)
    get_settings.cache_clear()

    from sqlalchemy import event, pool

    engine = create_async_engine(
        test_settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=pool.StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Point global session factory at test engine
    import app.db.session as session_mod

    session_mod._engine = engine
    session_mod._session_factory = session_factory

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_async_session] = _override_session

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    application.dependency_overrides.clear()
    await engine.dispose()
    session_mod._engine = None
    session_mod._session_factory = None
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = "owner@example.com"
    password = "securepassword123"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert reg.status_code == 201, reg.text

    login = await client.post(
        "/api/v1/auth/jwt/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
