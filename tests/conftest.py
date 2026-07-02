import pathlib
import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.db import get_conn, init_db
from main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        db_path=str(tmp_path / "test.db"),
        presave_url="https://presave.example/target",
        admin_user="admin",
        admin_pass="secret",
        secret_key="test-secret-key",
        public_base_url="http://testserver",
    )


@pytest.fixture(autouse=True)
def init_test_db(settings):
    """Initialize the test database schema for all tests."""
    conn = get_conn(settings.db_path)
    try:
        init_db(conn)
    finally:
        conn.close()


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))
