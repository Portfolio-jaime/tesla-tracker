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


class TestStepsAPI:
    def test_get_steps_returns_6(self):
        res_id = make_reservation()
        r = client.get(f"/api/v1/reservations/{res_id}/steps")
        assert r.status_code == 200
        steps = r.json()
        assert len(steps) == 6

    def test_get_steps_order(self):
        res_id = make_reservation()
        steps = client.get(f"/api/v1/reservations/{res_id}/steps").json()
        keys = [s["step_key"] for s in steps]
        assert keys == ["RESERVA", "CONFIRMACION", "PRODUCCION", "ENVIO_MARITIMO", "ADUANA", "ENTREGA"]

    def test_get_steps_idempotent(self):
        res_id = make_reservation()
        client.get(f"/api/v1/reservations/{res_id}/steps")
        r = client.get(f"/api/v1/reservations/{res_id}/steps")
        assert r.status_code == 200
        assert len(r.json()) == 6

    def test_get_steps_404_unknown_reservation(self):
        r = client.get("/api/v1/reservations/9999/steps")
        assert r.status_code == 404

    def test_get_steps_all_incomplete_by_default(self):
        res_id = make_reservation()
        steps = client.get(f"/api/v1/reservations/{res_id}/steps").json()
        assert all(not s["completed"] for s in steps)

    def test_patch_step_marks_completed(self):
        res_id = make_reservation()
        r = client.patch(
            f"/api/v1/reservations/{res_id}/steps/RESERVA",
            json={"completed": True, "completed_date": "2026-05-09T00:00:00", "notes": "RN128096402"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["completed"] is True
        assert data["notes"] == "RN128096402"
        assert "2026-05-09" in data["completed_date"]

    def test_patch_step_invalid_key(self):
        res_id = make_reservation()
        r = client.patch(f"/api/v1/reservations/{res_id}/steps/INVALID", json={"completed": True})
        assert r.status_code == 400

    def test_patch_step_404_unknown_reservation(self):
        r = client.patch("/api/v1/reservations/9999/steps/RESERVA", json={"completed": True})
        assert r.status_code == 404

    def test_patch_step_autoseeds_if_no_get_called(self):
        res_id = make_reservation()
        r = client.patch(
            f"/api/v1/reservations/{res_id}/steps/PRODUCCION",
            json={"completed": True},
        )
        assert r.status_code == 200
        assert r.json()["completed"] is True
