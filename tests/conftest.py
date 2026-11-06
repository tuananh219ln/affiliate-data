import os

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://affiliate:affiliate@localhost:5432/affiliate_test")
os.environ["API_KEY"] = "test-key"
os.environ["SECRET_KEY"] = Fernet.generate_key().decode()
# The test client talks plain http, where a Secure cookie would not be sent back.
os.environ["COOKIE_SECURE"] = "0"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from affiliate_data import accounts, models  # noqa: F401  (registers the tables)
from affiliate_data.db import Base, SessionLocal, engine
from affiliate_data.main import app

# Real cost would make each sign-in in the tests take a large fraction of a second.
accounts.SCRYPT_N = 2**10


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as connection:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY"))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app, headers={"X-API-Key": "test-key"})
