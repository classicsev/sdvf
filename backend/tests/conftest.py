import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, hash_password
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Account, Category, Counterparty, Project, RoleEnum, TxTypeEnum, User

TEST_DATABASE_URL = settings.database_url.rsplit("/", 1)[0] + "/finance_test_db"

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(scope="session", autouse=True)
def _setup_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


def _override_get_db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session():
    session = TestingSessionLocal()
    yield session
    session.close()


def make_user(db_session, role=RoleEnum.admin, project_id=None, email=None, password="test1234", is_active=True):
    email = email or f"{role.value}-{uuid.uuid4().hex[:8]}@test.local"
    user = User(
        email=email,
        full_name=f"Test {role.value}",
        hashed_password=hash_password(password),
        role=role,
        project_id=project_id,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_headers(user) -> dict:
    token = create_access_token({"sub": user.id, "role": user.role.value})
    return {"Authorization": f"Bearer {token}"}


def make_category(db_session, name="Тестовая статья", tx_type=TxTypeEnum.expense, group_name=None):
    category = Category(name=name, type=tx_type, group_name=group_name)
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


def make_account(db_session, name="Тестовый счёт", currency="RUB", opening_balance=0, account_number=None):
    account = Account(name=name, currency=currency, opening_balance=opening_balance, account_number=account_number)
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


def make_project(db_session, name="Тестовый проект"):
    project = Project(name=name)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def make_counterparty(db_session, name="Тестовый контрагент"):
    counterparty = Counterparty(name=name)
    db_session.add(counterparty)
    db_session.commit()
    db_session.refresh(counterparty)
    return counterparty
