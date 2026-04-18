import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import database as database_module
import main as main_module
from database import Base
from models import Good, Role, User


@pytest_asyncio.fixture
async def db_engine(tmp_path: Path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    return async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_session(session_factory):
    async with session_factory() as session:
        customer = User(
            openid="test_customer",
            role=Role.CUSTOMER,
            nickname="Test Customer",
            phone="13800000000",
        )
        merchant = User(
            openid="test_merchant_a",
            role=Role.MERCHANT,
            nickname="商家A",
            phone="13900000001",
        )
        merchant_b = User(
            openid="test_merchant_b",
            role=Role.MERCHANT,
            nickname="商家B",
            phone="13900000002",
        )
        good = Good(
            title="Seeded Massage",
            description="Seeded test good",
            price=19900,
            original_price=29900,
            duration=90,
            img_url="/static/test-good.jpg",
            sales=0,
            detail_images='["/static/detail-1.jpg"]',
        )

        session.add_all([customer, merchant, merchant_b, good])
        await session.commit()
        await session.refresh(customer)
        await session.refresh(merchant)
        await session.refresh(merchant_b)
        await session.refresh(good)

        session.info["seeded_data"] = {
            "customer": customer,
            "merchant": merchant,
            "merchant_b": merchant_b,
            "good": good,
            "merchant_contacts": [merchant, merchant_b],
        }
        yield session


@pytest.fixture
def seeded_data(seeded_session):
    return seeded_session.info["seeded_data"]


@pytest.fixture
def customer_user(seeded_data):
    return seeded_data["customer"]


@pytest.fixture
def merchant_user(seeded_data):
    return seeded_data["merchant"]


@pytest.fixture
def seeded_good(seeded_data):
    return seeded_data["good"]


@pytest.fixture
def merchant_contacts(seeded_data):
    return seeded_data["merchant_contacts"]


@pytest.fixture
def auth_headers(customer_user):
    return {"X-Token": customer_user.openid}


@pytest.fixture
def customer_headers(auth_headers):
    return auth_headers


@pytest.fixture
def merchant_headers(merchant_user):
    return {"X-Token": merchant_user.openid}


@pytest.fixture
def admin_headers():
    return {"X-Admin-Key": "qq5201314"}


@pytest.fixture
def app(seeded_session):
    async def override_get_db():
        yield seeded_session

    main_module.app.dependency_overrides[database_module.get_db] = override_get_db
    main_module.app.dependency_overrides[main_module.get_db] = override_get_db

    yield main_module.app

    main_module.app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app, seeded_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
