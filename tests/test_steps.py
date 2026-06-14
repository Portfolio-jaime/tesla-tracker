# tests/test_steps.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.main import app
from app.database.database import get_db
from app.database.models import Base, PurchaseStep, STEP_KEYS

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_steps.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def make_reservation():
    r = client.post("/api/v1/reservations", json={"model": "Model Y", "color": "Gris Grafito"})
    assert r.status_code == 201
    return r.json()["id"]


class TestPurchaseStepModel:
    def test_step_keys_are_6(self):
        assert len(STEP_KEYS) == 6

    def test_step_keys_values(self):
        assert STEP_KEYS == [
            "RESERVA", "CONFIRMACION", "PRODUCCION",
            "ENVIO_MARITIMO", "ADUANA", "ENTREGA",
        ]

    def test_purchase_step_table_exists(self):
        db = TestingSessionLocal()
        try:
            count = db.query(PurchaseStep).count()
            assert count == 0
        finally:
            db.close()
