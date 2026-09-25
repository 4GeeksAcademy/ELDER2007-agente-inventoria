import pytest
from fastapi.testclient import TestClient

import agent_lib.logger as logger_module
from api import storage
from api.app import app


@pytest.fixture(autouse=True)
def aislar_datos(tmp_path, monkeypatch):
    """Cada test usa CSV y log temporales y una API sin clave, para no tocar datos reales."""
    monkeypatch.setattr(storage, "CSV_PATH", tmp_path / "products.csv")
    monkeypatch.setattr(logger_module, "LOG_PATH", tmp_path / "conversation_log.csv")
    monkeypatch.delenv("API_KEY", raising=False)


@pytest.fixture
def client():
    return TestClient(app)
