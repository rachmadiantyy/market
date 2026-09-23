"""Test fixtures.

Tests run against a real PostgreSQL instance (the compose `postgres` service)
using a separate `affiliate_test` database, and against an in-memory fake Redis.
"""

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.redis as redis_module
import app.models  # noqa: F401  (register models on Base.metadata)
from app.core.config import settings
from app.core.database import Base, get_db
from app.providers.ai.base import AIProvider

TEST_DATABASE = "affiliate_test"


def _url_for(database: str) -> str:
    """Render the configured DB URL with credentials intact."""
    return make_url(settings.database_url).set(database=database).render_as_string(
        hide_password=False
    )


@pytest_asyncio.fixture
async def engine():
    admin_url = _url_for("postgres")
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DATABASE},
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    await admin_engine.dispose()

    test_engine = create_async_engine(_url_for(TEST_DATABASE), pool_pre_ping=True)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def fake_redis():
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    original = redis_module._redis
    redis_module._redis = fake
    try:
        yield fake
    finally:
        redis_module._redis = original
        await fake.aclose()


@pytest_asyncio.fixture
async def client(session_factory, fake_redis):
    from app.main import app

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class StubProvider(AIProvider):
    """Controllable provider for tests."""

    name = "stub"

    def __init__(self, *, output: str | None = None, error: Exception | None = None):
        self.model = "stub-model"
        self._output = output if output is not None else '{"variations": ["hasil"]}'
        self._error = error
        self.calls = 0

    async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._output


@pytest.fixture
def stub_provider():
    return StubProvider


# Re-export Telegram fixtures so they are available to every test module.
from tests.telegram_helpers import bot_ctx, bot_settings  # noqa: E402,F401
