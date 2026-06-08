import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.main import app
from app.database.database import get_db
from app.database.models import Base
from app.database.schemas import ReservationCreate

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
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
    """Clean up database before each test"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


class TestHealth:
    """Health check tests"""
    
    def test_root(self):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "running"
    
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestReservationsCRUD:
    """Reservation CRUD tests"""
    
    def test_create_reservation(self):
        reservation_data = {
            "model": "Model 3",
            "color": "Solid Black",
            "wheels": "18\" Aero",
            "status": "CONFIRMED"
        }
        
        response = client.post("/api/v1/reservations", json=reservation_data)
        assert response.status_code == 201
        data = response.json()
        assert data["model"] == "Model 3"
        assert data["id"] is not None
    
    def test_create_reservation_with_vin(self):
        reservation_data = {
            "model": "Model 3",
            "vin": "5YJ3E1EA1KF123456"
        }
        
        response = client.post("/api/v1/reservations", json=reservation_data)
        assert response.status_code == 201
        data = response.json()
        assert data["vin"] == "5YJ3E1EA1KF123456"
    
    def test_create_duplicate_vin(self):
        reservation_data = {
            "model": "Model 3",
            "vin": "5YJ3E1EA1KF123456"
        }
        
        # Create first
        response1 = client.post("/api/v1/reservations", json=reservation_data)
        assert response1.status_code == 201
        
        # Try to create duplicate
        response2 = client.post("/api/v1/reservations", json=reservation_data)
        assert response2.status_code == 400
    
    def test_get_reservations(self):
        # Create 3 reservations
        for i in range(3):
            client.post("/api/v1/reservations", json={
                "model": f"Model {i}",
                "status": "CONFIRMED"
            })
        
        response = client.get("/api/v1/reservations")
        assert response.status_code == 200
        assert len(response.json()) == 3
    
    def test_get_reservation_by_id(self):
        # Create a reservation
        create_response = client.post("/api/v1/reservations", json={
            "model": "Model 3"
        })
        reservation_id = create_response.json()["id"]
        
        # Get it
        response = client.get(f"/api/v1/reservations/{reservation_id}")
        assert response.status_code == 200
        assert response.json()["id"] == reservation_id
    
    def test_get_nonexistent_reservation(self):
        response = client.get("/api/v1/reservations/999")
        assert response.status_code == 404
    
    def test_update_reservation(self):
        # Create
        create_response = client.post("/api/v1/reservations", json={
            "model": "Model 3",
            "status": "CONFIRMED"
        })
        reservation_id = create_response.json()["id"]
        
        # Update
        response = client.put(
            f"/api/v1/reservations/{reservation_id}",
            json={"status": "DELIVERED"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "DELIVERED"
    
    def test_delete_reservation(self):
        # Create
        create_response = client.post("/api/v1/reservations", json={
            "model": "Model 3"
        })
        reservation_id = create_response.json()["id"]
        
        # Delete
        response = client.delete(f"/api/v1/reservations/{reservation_id}")
        assert response.status_code == 204
        
        # Verify deleted
        response = client.get(f"/api/v1/reservations/{reservation_id}")
        assert response.status_code == 404
    
    def test_get_reservations_filter_by_status(self):
        # Create with different statuses
        client.post("/api/v1/reservations", json={
            "model": "Model 3",
            "status": "CONFIRMED"
        })
        client.post("/api/v1/reservations", json={
            "model": "Model Y",
            "status": "DELIVERED"
        })
        
        # Filter
        response = client.get("/api/v1/reservations?status=CONFIRMED")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["status"] == "CONFIRMED"
    
    def test_get_reservations_filter_by_model(self):
        # Create with different models
        client.post("/api/v1/reservations", json={"model": "Model 3"})
        client.post("/api/v1/reservations", json={"model": "Model Y"})
        client.post("/api/v1/reservations", json={"model": "Model S"})
        
        # Filter
        response = client.get("/api/v1/reservations?model=Model%203")
        assert response.status_code == 200
        assert len(response.json()) == 1


class TestStats:
    """Statistics tests"""
    
    def test_get_stats(self):
        # Create some reservations
        client.post("/api/v1/reservations", json={
            "model": "Model 3",
            "status": "CONFIRMED"
        })
        client.post("/api/v1/reservations", json={
            "model": "Model Y",
            "status": "DELIVERED"
        })
        
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert "by_status" in data
        assert "by_model" in data
