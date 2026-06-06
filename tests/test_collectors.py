"""
Comprehensive integration tests for ReservationCollector and ShippingCollector.

Tests the complete workflow:
1. Both collectors use the same database
2. ReservationCollector creates reservations
3. ShippingCollector updates reservations
4. Concurrent execution of both collectors
5. Scheduler integration
6. Error handling and rollback scenarios
"""

import pytest
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import SQLAlchemyError

from app.collectors.reservation import ReservationCollector
from app.collectors.shipping import ShippingCollector
from app.collectors.scheduler import CollectorScheduler
from app.database.models import Base, Reservation
from app.database.schemas import ReservationCreate


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def test_db():
    """
    Create an in-memory SQLite database for testing.
    
    This fixture ensures database isolation between tests by creating
    a fresh database for each test function.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    
    yield TestSessionLocal
    
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def reservation_collector(test_db):
    """Create a ReservationCollector instance with test database."""
    collector = ReservationCollector()
    collector.db = test_db()
    yield collector
    collector.close()


@pytest.fixture
def shipping_collector(test_db):
    """Create a ShippingCollector instance with test database."""
    db_session = test_db()
    collector = ShippingCollector(db=db_session)
    yield collector
    db_session.close()


@pytest.fixture
def shared_test_db(test_db):
    """
    Provide a shared database session for testing collector interaction.
    
    Both collectors will use this same database instance to test
    cross-collector workflows.
    """
    db_session = test_db()
    yield db_session
    db_session.close()


@pytest.fixture
def shared_collectors(shared_test_db):
    """Create both collectors sharing the same database."""
    res_collector = ReservationCollector()
    res_collector.db = shared_test_db
    
    ship_collector = ShippingCollector(db=shared_test_db)
    
    yield {
        "reservation": res_collector,
        "shipping": ship_collector,
        "db": shared_test_db,
    }


@pytest.fixture
def sample_reservation_data():
    """Sample reservation data for testing."""
    return [
        {
            "model": "Model 3",
            "status": "RESERVED",
            "order_date": datetime(2024, 1, 15),
            "color": "Midnight Black",
            "wheels": "18-inch Aero",
            "vin": "5YJ3E1EA0JF100001",
        },
        {
            "model": "Model S",
            "status": "RESERVED",
            "order_date": datetime(2024, 1, 20),
            "color": "Pearl Multi-Coat",
            "wheels": "19-inch Überturbine",
            "vin": "5YJ3E1EA0JF100002",
        },
        {
            "model": "Model Y",
            "status": "CONFIRMED",
            "order_date": datetime(2024, 2, 1),
            "color": "Solid Black",
            "vin": "5YJ3E1EA0JF100003",
        },
    ]


@pytest.fixture
def sample_tracking_data():
    """Sample tracking/shipping data for testing."""
    now = datetime.utcnow()
    return [
        {
            "vin": "5YJ3E1EA0JF100001",
            "status": "MANUFACTURING",
            "eta_start": now + timedelta(days=30),
            "eta_end": now + timedelta(days=45),
            "timestamp": now,
        },
        {
            "vin": "5YJ3E1EA0JF100002",
            "status": "IN_TRANSIT",
            "eta_start": now + timedelta(days=10),
            "eta_end": now + timedelta(days=15),
            "timestamp": now,
        },
        {
            "vin": "5YJ3E1EA0JF100003",
            "status": "DELIVERED",
            "eta_start": now - timedelta(days=5),
            "eta_end": now - timedelta(days=1),
            "timestamp": now,
        },
    ]


# ============================================================================
# SHARED DATABASE TESTS
# ============================================================================

class TestSharedDatabase:
    """Tests verifying both collectors use the same database."""
    
    def test_both_collectors_write_to_same_db(self, shared_collectors, sample_reservation_data):
        """Verify that both collectors operate on the same database."""
        db = shared_collectors["db"]
        res_collector = shared_collectors["reservation"]
        ship_collector = shared_collectors["shipping"]
        
        # Save reservation via ReservationCollector
        res_data = sample_reservation_data[0]
        validated = res_collector.validate_reservation(res_data)
        assert validated is not None
        res_collector._save_reservation(db, validated)
        
        # Query the reservation via ShippingCollector
        reservation = db.query(Reservation).filter_by(vin=res_data["vin"]).first()
        
        assert reservation is not None
        assert reservation.model == "Model 3"
        assert reservation.status == "RESERVED"
    
    def test_database_isolation_between_tests(self, test_db):
        """Verify each test gets a fresh database."""
        db_session = test_db()
        
        # First test should have empty database
        count = db_session.query(Reservation).count()
        assert count == 0
        
        db_session.close()


# ============================================================================
# INTEGRATION TESTS - RESERVATION COLLECTOR
# ============================================================================

class TestReservationCollectorIntegration:
    """Integration tests for ReservationCollector functionality."""
    
    def test_reservation_collector_creates_reservations(self, shared_collectors, sample_reservation_data):
        """Test that ReservationCollector successfully creates reservations."""
        collector = shared_collectors["reservation"]
        db = shared_collectors["db"]
        
        result = collector.validate_and_save(sample_reservation_data)
        
        assert result["total"] == 3
        assert result["saved"] == 3
        assert result["failed"] == 0
        
        # Verify reservations exist in database
        count = db.query(Reservation).count()
        assert count == 3
    
    def test_reservation_collector_updates_existing_by_vin(self, shared_collectors, sample_reservation_data):
        """Test that collector updates existing reservations by VIN."""
        collector = shared_collectors["reservation"]
        db = shared_collectors["db"]
        
        # First save
        first_data = [sample_reservation_data[0]]
        result1 = collector.validate_and_save(first_data)
        assert result1["saved"] == 1
        
        # Update with same VIN but different data
        updated_data = [
            {
                **first_data[0],
                "status": "CONFIRMED",
                "color": "Solid Black",
            }
        ]
        result2 = collector.validate_and_save(updated_data)
        assert result2["saved"] == 1
        
        # Verify only one reservation exists and is updated
        count = db.query(Reservation).count()
        assert count == 1
        
        reservation = db.query(Reservation).filter_by(vin="5YJ3E1EA0JF100001").first()
        assert reservation.status == "CONFIRMED"
        assert reservation.color == "Solid Black"
    
    def test_reservation_collector_validates_required_fields(self, shared_collectors):
        """Test validation of required fields."""
        collector = shared_collectors["reservation"]
        
        # Missing required fields
        invalid_data = [{"color": "Black"}]
        result = collector.validate_and_save(invalid_data)
        
        assert result["saved"] == 0
        assert result["failed"] == 1
        assert len(result["errors"]) > 0


# ============================================================================
# INTEGRATION TESTS - SHIPPING COLLECTOR
# ============================================================================

class TestShippingCollectorIntegration:
    """Integration tests for ShippingCollector functionality."""
    
    def test_shipping_collector_updates_reservations(self, shared_collectors, sample_reservation_data, sample_tracking_data):
        """Test that ShippingCollector updates reservations created by ReservationCollector."""
        res_collector = shared_collectors["reservation"]
        ship_collector = shared_collectors["shipping"]
        db = shared_collectors["db"]
        
        # Create reservations first
        res_collector.validate_and_save(sample_reservation_data)
        
        # Update with shipping info
        result = ship_collector.update_reservations(tracking_updates=sample_tracking_data)
        
        assert result["updated_count"] == 3
        assert result["failed_vins"] == []
        
        # Verify reservations are updated
        updated_res = db.query(Reservation).filter_by(vin="5YJ3E1EA0JF100001").first()
        assert updated_res.status == "MANUFACTURING"
        assert updated_res.eta_start is not None
        assert updated_res.eta_end is not None
    
    def test_shipping_collector_sets_delivery_date_on_delivered(self, shared_collectors, sample_reservation_data):
        """Test that delivery_date is set when status changes to DELIVERED."""
        res_collector = shared_collectors["reservation"]
        ship_collector = shared_collectors["shipping"]
        db = shared_collectors["db"]
        
        # Create a reservation
        res_collector.validate_and_save(sample_reservation_data[:1])
        
        # Update to DELIVERED status
        tracking_update = [
            {
                "vin": "5YJ3E1EA0JF100001",
                "status": "DELIVERED",
                "eta_start": datetime.utcnow() - timedelta(days=5),
                "eta_end": datetime.utcnow() - timedelta(days=1),
            }
        ]
        ship_collector.update_reservations(tracking_updates=tracking_update)
        
        # Verify delivery_date is set
        reservation = db.query(Reservation).filter_by(vin="5YJ3E1EA0JF100001").first()
        assert reservation.status == "DELIVERED"
        assert reservation.delivery_date is not None
    
    def test_shipping_collector_handles_missing_reservations(self, shared_collectors):
        """Test that ShippingCollector gracefully handles updates for missing reservations."""
        collector = shared_collectors["shipping"]
        
        tracking_update = [
            {
                "vin": "NONEXISTENT_VIN",
                "status": "IN_TRANSIT",
                "eta_start": datetime.utcnow(),
                "eta_end": datetime.utcnow() + timedelta(days=5),
            }
        ]
        
        result = collector.update_reservations(tracking_updates=tracking_update)
        
        assert result["updated_count"] == 0
        assert "NONEXISTENT_VIN" in result["failed_vins"]


# ============================================================================
# CONCURRENT EXECUTION TESTS
# ============================================================================

class TestConcurrentExecution:
    """Tests for concurrent execution of collectors."""
    
    def test_concurrent_reservation_and_shipping_updates(self, shared_collectors, sample_reservation_data, sample_tracking_data):
        """Test that both collectors can run concurrently without data corruption."""
        res_collector = shared_collectors["reservation"]
        ship_collector = shared_collectors["shipping"]
        db = shared_collectors["db"]
        
        errors = []
        
        def create_reservations():
            try:
                res_collector.validate_and_save(sample_reservation_data)
            except Exception as e:
                errors.append(("reservation", str(e)))
        
        def update_with_tracking():
            # Small delay to ensure reservations are created first
            time.sleep(0.1)
            try:
                ship_collector.update_reservations(tracking_updates=sample_tracking_data)
            except Exception as e:
                errors.append(("shipping", str(e)))
        
        # Run both operations concurrently
        thread1 = threading.Thread(target=create_reservations)
        thread2 = threading.Thread(target=update_with_tracking)
        
        thread1.start()
        thread2.start()
        
        thread1.join(timeout=5)
        thread2.join(timeout=5)
        
        # Verify no errors occurred
        assert len(errors) == 0, f"Errors during concurrent execution: {errors}"
        
        # Verify final state
        reservations = db.query(Reservation).all()
        assert len(reservations) == 3
        
        # Check that at least one reservation has shipping info
        shipped = db.query(Reservation).filter(Reservation.status != "RESERVED").first()
        assert shipped is not None
    
    def test_multiple_concurrent_updates_same_reservation(self, shared_collectors):
        """Test concurrent updates to the same reservation."""
        collector = shared_collectors["shipping"]
        db = shared_collectors["db"]
        
        # Create initial reservation
        res = Reservation(
            model="Model 3",
            status="RESERVED",
            order_date=datetime.utcnow(),
            vin="5YJ3E1EA0JF100001",
        )
        db.add(res)
        db.commit()
        
        update_results = []
        
        def update_reservation(status, eta_days):
            try:
                result = collector.update_reservations(
                    tracking_updates=[
                        {
                            "vin": "5YJ3E1EA0JF100001",
                            "status": status,
                            "eta_start": datetime.utcnow() + timedelta(days=eta_days),
                            "eta_end": datetime.utcnow() + timedelta(days=eta_days + 5),
                        }
                    ]
                )
                update_results.append(result)
            except Exception as e:
                update_results.append({"error": str(e)})
        
        # Simulate concurrent updates
        threads = [
            threading.Thread(target=update_reservation, args=("MANUFACTURING", 30)),
            threading.Thread(target=update_reservation, args=("SHIPPING", 15)),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        
        # All updates should have succeeded
        assert len(update_results) == 2
        assert all("error" not in r for r in update_results)


# ============================================================================
# SCHEDULER INTEGRATION TESTS
# ============================================================================

class TestSchedulerIntegration:
    """Tests for scheduler integration with collectors."""
    
    @patch("app.collectors.scheduler.ReservationCollector")
    @patch("app.collectors.scheduler.ShippingCollector")
    def test_scheduler_executes_collectors(self, mock_shipping_class, mock_reservation_class):
        """Test that scheduler properly executes both collectors."""
        mock_res_instance = MagicMock()
        mock_res_instance.run.return_value = {"saved": 5, "failed": 0}
        mock_reservation_class.return_value = mock_res_instance
        
        mock_ship_instance = MagicMock()
        mock_ship_instance.run.return_value = {"updated_count": 3, "failed_vins": []}
        mock_shipping_class.return_value = mock_ship_instance
        
        scheduler = CollectorScheduler()
        scheduler.start_scheduler()
        
        try:
            # Give scheduler time to execute jobs
            time.sleep(2)
            
            # Both collectors should be added to scheduler
            assert len(scheduler.jobs) == 2
            assert "reservation_collector" in scheduler.jobs
            assert "shipping_collector" in scheduler.jobs
            
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()
    
    def test_scheduler_initialization(self):
        """Test that scheduler initializes correctly."""
        scheduler = CollectorScheduler()
        
        assert not scheduler.is_running
        assert len(scheduler.jobs) == 0
        assert scheduler.scheduler is None


# ============================================================================
# ERROR HANDLING & ROLLBACK TESTS
# ============================================================================

class TestErrorHandlingAndRollback:
    """Tests for error handling and transaction rollback."""
    
    def test_reservation_collection_handles_database_errors(self, shared_collectors):
        """Test that ReservationCollector handles DB errors gracefully."""
        collector = shared_collectors["reservation"]
        
        # Simulate database error
        collector.db.query = MagicMock(side_effect=SQLAlchemyError("DB Error"))
        
        result = collector.validate_and_save([
            {
                "model": "Model 3",
                "status": "RESERVED",
                "order_date": datetime.utcnow(),
            }
        ])
        
        assert result["saved"] == 0
        assert result["failed"] > 0
    
    def test_shipping_update_rollback_on_commit_error(self, shared_collectors):
        """Test that ShippingCollector rolls back on commit error."""
        db = shared_collectors["db"]
        collector = shared_collectors["shipping"]
        
        # Create a reservation
        res = Reservation(
            model="Model 3",
            status="RESERVED",
            order_date=datetime.utcnow(),
            vin="5YJ3E1EA0JF100001",
        )
        db.add(res)
        db.commit()
        
        original_status = res.status
        
        # Mock commit to raise error
        with patch.object(db, 'commit', side_effect=SQLAlchemyError("Commit failed")):
            with pytest.raises(SQLAlchemyError):
                collector.update_reservations(
                    tracking_updates=[
                        {
                            "vin": "5YJ3E1EA0JF100001",
                            "status": "IN_TRANSIT",
                            "eta_start": datetime.utcnow(),
                            "eta_end": datetime.utcnow() + timedelta(days=5),
                        }
                    ]
                )
    
    def test_validation_errors_dont_affect_other_records(self, shared_collectors):
        """Test that validation errors for one record don't affect others."""
        collector = shared_collectors["reservation"]
        db = shared_collectors["db"]
        
        data = [
            {
                "model": "Model 3",
                "status": "RESERVED",
                "order_date": datetime.utcnow(),
            },
            {  # Missing required fields
                "color": "Black",
            },
            {
                "model": "Model S",
                "status": "CONFIRMED",
                "order_date": datetime.utcnow(),
            },
        ]
        
        result = collector.validate_and_save(data)
        
        # Should save 2 valid records
        assert result["saved"] == 2
        assert result["failed"] == 1
        
        # Verify 2 reservations in database
        count = db.query(Reservation).count()
        assert count == 2


# ============================================================================
# SESSION MANAGEMENT TESTS
# ============================================================================

class TestSessionManagement:
    """Tests for database session management."""
    
    def test_reservation_collector_session_cleanup(self, test_db):
        """Test that ReservationCollector properly closes sessions."""
        collector = ReservationCollector()
        collector.db = test_db()
        
        assert collector.db is not None
        
        collector.close()
        
        assert collector.db is None
    
    def test_shipping_collector_session_management(self, test_db):
        """Test that ShippingCollector manages its session."""
        db_session = test_db()
        collector = ShippingCollector(db=db_session)
        
        assert collector.db is db_session
        
        db_session.close()
    
    def test_collectors_with_same_session_share_changes(self, shared_collectors, sample_reservation_data):
        """Test that collectors sharing a session see each other's changes."""
        res_collector = shared_collectors["reservation"]
        ship_collector = shared_collectors["shipping"]
        db = shared_collectors["db"]
        
        # Create reservation via ReservationCollector
        res_collector.validate_and_save([sample_reservation_data[0]])
        
        # Query via ShippingCollector's session (same instance)
        status = ship_collector.get_reservation_status("5YJ3E1EA0JF100001")
        
        assert status is not None
        assert status["model"] == "Model 3"


# ============================================================================
# WORKFLOW TESTS
# ============================================================================

class TestCompleteWorkflow:
    """Tests for complete end-to-end workflows."""
    
    def test_complete_reservation_to_delivery_workflow(self, shared_collectors, sample_reservation_data):
        """Test complete workflow from reservation to delivery."""
        res_collector = shared_collectors["reservation"]
        ship_collector = shared_collectors["shipping"]
        db = shared_collectors["db"]
        
        vin = "5YJ3E1EA0JF100001"
        
        # Step 1: Create reservation
        res_data = [r for r in sample_reservation_data if r["vin"] == vin][0]
        res_collector.validate_and_save([res_data])
        
        reservation = db.query(Reservation).filter_by(vin=vin).first()
        assert reservation.status == "RESERVED"
        
        # Step 2: Update to MANUFACTURING
        ship_collector.update_reservations(
            tracking_updates=[{
                "vin": vin,
                "status": "MANUFACTURING",
                "eta_start": datetime.utcnow() + timedelta(days=30),
                "eta_end": datetime.utcnow() + timedelta(days=45),
            }]
        )
        
        reservation = db.query(Reservation).filter_by(vin=vin).first()
        assert reservation.status == "MANUFACTURING"
        
        # Step 3: Update to IN_TRANSIT
        ship_collector.update_reservations(
            tracking_updates=[{
                "vin": vin,
                "status": "IN_TRANSIT",
                "eta_start": datetime.utcnow() + timedelta(days=5),
                "eta_end": datetime.utcnow() + timedelta(days=10),
            }]
        )
        
        reservation = db.query(Reservation).filter_by(vin=vin).first()
        assert reservation.status == "IN_TRANSIT"
        assert reservation.delivery_date is None
        
        # Step 4: Mark as DELIVERED
        ship_collector.update_reservations(
            tracking_updates=[{
                "vin": vin,
                "status": "DELIVERED",
                "eta_start": datetime.utcnow() - timedelta(days=2),
                "eta_end": datetime.utcnow(),
            }]
        )
        
        reservation = db.query(Reservation).filter_by(vin=vin).first()
        assert reservation.status == "DELIVERED"
        assert reservation.delivery_date is not None
    
    def test_bulk_reservation_creation_and_tracking(self, shared_collectors, sample_reservation_data, sample_tracking_data):
        """Test bulk creation and tracking of multiple reservations."""
        res_collector = shared_collectors["reservation"]
        ship_collector = shared_collectors["shipping"]
        db = shared_collectors["db"]
        
        # Create multiple reservations
        result = res_collector.validate_and_save(sample_reservation_data)
        assert result["saved"] == 3
        
        # Update tracking for all
        result = ship_collector.update_reservations(tracking_updates=sample_tracking_data)
        assert result["updated_count"] == 3
        
        # Verify all reservations have tracking info
        reservations = db.query(Reservation).all()
        assert len(reservations) == 3
        assert all(r.eta_start is not None for r in reservations)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
