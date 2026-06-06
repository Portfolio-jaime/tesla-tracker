"""
Tests for ShippingCollector.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.collectors.shipping import ShippingCollector
from app.database.models import Reservation


class TestShippingCollectorTracking:
    """Tests for get_tracking_updates method."""

    def test_get_tracking_updates_returns_list(self):
        """Test that get_tracking_updates returns a list."""
        collector = ShippingCollector(db=MagicMock(spec=Session))
        updates = collector.get_tracking_updates()

        assert isinstance(updates, list)
        assert len(updates) > 0

    def test_get_tracking_updates_contains_required_fields(self):
        """Test that tracking updates contain required fields."""
        collector = ShippingCollector(db=MagicMock(spec=Session))
        updates = collector.get_tracking_updates()

        required_fields = ["vin", "status", "eta_start", "eta_end", "timestamp"]
        for update in updates:
            for field in required_fields:
                assert field in update, f"Missing field: {field}"

    def test_get_tracking_updates_filter_by_vin(self):
        """Test filtering tracking updates by VIN."""
        collector = ShippingCollector(db=MagicMock(spec=Session))
        vin = "5TDJVRF33LS123456"
        updates = collector.get_tracking_updates(vin=vin)

        assert len(updates) > 0
        assert all(u["vin"] == vin for u in updates)

    def test_get_tracking_updates_unknown_vin(self):
        """Test get_tracking_updates with unknown VIN returns empty list."""
        collector = ShippingCollector(db=MagicMock(spec=Session))
        updates = collector.get_tracking_updates(vin="UNKNOWN_VIN_12345")

        assert isinstance(updates, list)
        assert len(updates) == 0

    def test_get_tracking_updates_valid_statuses(self):
        """Test that all returned tracking updates have valid statuses."""
        collector = ShippingCollector(db=MagicMock(spec=Session))
        updates = collector.get_tracking_updates()

        for update in updates:
            assert update["status"] in collector.VALID_STATUSES


class TestShippingCollectorUpdateReservations:
    """Tests for update_reservations method."""

    def test_update_reservations_with_provided_data(self):
        """Test updating reservations with provided tracking data."""
        mock_db = MagicMock(spec=Session)
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.status = "CONFIRMED"
        mock_reservation.vin = "5TDJVRF33LS123456"

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_reservation
        )

        collector = ShippingCollector(db=mock_db)

        tracking_updates = [
            {
                "vin": "5TDJVRF33LS123456",
                "status": "IN_TRANSIT",
                "eta_start": datetime.utcnow() + timedelta(days=2),
                "eta_end": datetime.utcnow() + timedelta(days=5),
            }
        ]

        result = collector.update_reservations(tracking_updates=tracking_updates)

        assert result["updated_count"] == 1
        assert result["failed_vins"] == []
        assert mock_db.commit.called

    def test_update_reservations_missing_vin(self):
        """Test handling of tracking updates with missing VIN."""
        mock_db = MagicMock(spec=Session)
        collector = ShippingCollector(db=mock_db)

        tracking_updates = [
            {
                "status": "IN_TRANSIT",
                "eta_start": datetime.utcnow() + timedelta(days=2),
            }
        ]

        result = collector.update_reservations(tracking_updates=tracking_updates)

        assert result["updated_count"] == 0
        assert len(result["errors"]) > 0

    def test_update_reservations_vin_not_found(self):
        """Test handling when reservation VIN not found in database."""
        mock_db = MagicMock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        collector = ShippingCollector(db=mock_db)

        tracking_updates = [
            {
                "vin": "NONEXISTENT_VIN_123",
                "status": "IN_TRANSIT",
                "eta_start": datetime.utcnow() + timedelta(days=2),
                "eta_end": datetime.utcnow() + timedelta(days=5),
            }
        ]

        result = collector.update_reservations(tracking_updates=tracking_updates)

        assert result["updated_count"] == 0
        assert "NONEXISTENT_VIN_123" in result["failed_vins"]
        assert len(result["errors"]) > 0

    def test_update_reservations_invalid_status(self):
        """Test handling of invalid status in tracking update."""
        mock_db = MagicMock(spec=Session)
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.status = "CONFIRMED"
        mock_reservation.vin = "5TDJVRF33LS123456"
        mock_reservation.eta_start = None
        mock_reservation.eta_end = None

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_reservation
        )

        collector = ShippingCollector(db=mock_db)

        tracking_updates = [
            {
                "vin": "5TDJVRF33LS123456",
                "status": "INVALID_STATUS",
                "eta_start": datetime.utcnow() + timedelta(days=2),
                "eta_end": datetime.utcnow() + timedelta(days=5),
            }
        ]

        result = collector.update_reservations(tracking_updates=tracking_updates)

        # Should still update but keep original status
        assert result["updated_count"] == 1
        assert len(result["errors"]) == 0

    def test_update_reservations_sets_delivery_date_on_delivered(self):
        """Test that delivery_date is set when status is DELIVERED."""
        mock_db = MagicMock(spec=Session)
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.status = "IN_TRANSIT"
        mock_reservation.vin = "5TDJVRF33LS123456"
        mock_reservation.eta_start = datetime.utcnow()
        mock_reservation.eta_end = datetime.utcnow()

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_reservation
        )

        collector = ShippingCollector(db=mock_db)

        tracking_updates = [
            {
                "vin": "5TDJVRF33LS123456",
                "status": "DELIVERED",
                "eta_start": datetime.utcnow(),
                "eta_end": datetime.utcnow(),
            }
        ]

        result = collector.update_reservations(tracking_updates=tracking_updates)

        assert result["updated_count"] == 1
        assert mock_reservation.delivery_date is not None

    def test_update_reservations_transaction_rollback(self):
        """Test that transaction is rolled back on commit error."""
        mock_db = MagicMock(spec=Session)
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.status = "CONFIRMED"
        mock_reservation.vin = "5TDJVRF33LS123456"
        mock_reservation.eta_start = None
        mock_reservation.eta_end = None

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_reservation
        )
        mock_db.commit.side_effect = SQLAlchemyError("Database error")

        collector = ShippingCollector(db=mock_db)

        tracking_updates = [
            {
                "vin": "5TDJVRF33LS123456",
                "status": "IN_TRANSIT",
                "eta_start": datetime.utcnow() + timedelta(days=2),
                "eta_end": datetime.utcnow() + timedelta(days=5),
            }
        ]

        with pytest.raises(SQLAlchemyError):
            collector.update_reservations(tracking_updates=tracking_updates)

        assert mock_db.rollback.called

    def test_update_reservations_empty_list(self):
        """Test update_reservations with empty tracking updates."""
        mock_db = MagicMock(spec=Session)
        collector = ShippingCollector(db=mock_db)

        result = collector.update_reservations(tracking_updates=[])

        assert result["updated_count"] == 0
        assert result["failed_vins"] == []
        assert len(result["errors"]) == 0


class TestShippingCollectorReservationStatus:
    """Tests for get_reservation_status method."""

    def test_get_reservation_status_found(self):
        """Test retrieving status of an existing reservation."""
        mock_db = MagicMock(spec=Session)
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.id = 1
        mock_reservation.vin = "5TDJVRF33LS123456"
        mock_reservation.model = "Model 3"
        mock_reservation.status = "IN_TRANSIT"
        mock_reservation.eta_start = datetime.utcnow()
        mock_reservation.eta_end = datetime.utcnow() + timedelta(days=5)
        mock_reservation.delivery_date = None
        mock_reservation.order_date = datetime.utcnow() - timedelta(days=30)

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_reservation
        )

        collector = ShippingCollector(db=mock_db)
        status = collector.get_reservation_status("5TDJVRF33LS123456")

        assert status is not None
        assert status["vin"] == "5TDJVRF33LS123456"
        assert status["status"] == "IN_TRANSIT"

    def test_get_reservation_status_not_found(self):
        """Test retrieving status of a non-existent reservation."""
        mock_db = MagicMock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        collector = ShippingCollector(db=mock_db)
        status = collector.get_reservation_status("NONEXISTENT_VIN")

        assert status is None


class TestShippingCollectorAdvanceStatus:
    """Tests for advance_reservation_status method."""

    def test_advance_reservation_status_success(self):
        """Test advancing reservation status in progression."""
        mock_db = MagicMock(spec=Session)
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.id = 1
        mock_reservation.vin = "5TDJVRF33LS123456"
        mock_reservation.model = "Model 3"
        mock_reservation.status = "CONFIRMED"
        mock_reservation.eta_start = datetime.utcnow()
        mock_reservation.eta_end = datetime.utcnow() + timedelta(days=5)
        mock_reservation.delivery_date = None
        mock_reservation.order_date = datetime.utcnow()

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_reservation
        )

        collector = ShippingCollector(db=mock_db)
        result = collector.advance_reservation_status("5TDJVRF33LS123456")

        assert result is not None
        assert mock_db.commit.called
        assert mock_reservation.status == "MANUFACTURING"

    def test_advance_reservation_status_at_final(self):
        """Test error when advancing from final status."""
        mock_db = MagicMock(spec=Session)
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.status = "DELIVERED"
        mock_reservation.vin = "5TDJVRF33LS123456"

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_reservation
        )

        collector = ShippingCollector(db=mock_db)

        with pytest.raises(ValueError):
            collector.advance_reservation_status("5TDJVRF33LS123456")

    def test_advance_reservation_status_not_found(self):
        """Test advancing status of non-existent reservation."""
        mock_db = MagicMock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        collector = ShippingCollector(db=mock_db)
        result = collector.advance_reservation_status("NONEXISTENT_VIN")

        assert result is None

    def test_advance_reservation_status_sets_delivery_date(self):
        """Test that delivery_date is set when advancing to DELIVERED."""
        mock_db = MagicMock(spec=Session)
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.status = "IN_TRANSIT"
        mock_reservation.vin = "5TDJVRF33LS123456"
        mock_reservation.id = 1
        mock_reservation.model = "Model 3"
        mock_reservation.eta_start = datetime.utcnow()
        mock_reservation.eta_end = datetime.utcnow()
        mock_reservation.delivery_date = None
        mock_reservation.order_date = datetime.utcnow()

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_reservation
        )

        collector = ShippingCollector(db=mock_db)
        collector.advance_reservation_status("5TDJVRF33LS123456")

        assert mock_reservation.delivery_date is not None


class TestShippingCollectorByStatus:
    """Tests for get_reservations_by_status method."""

    def test_get_reservations_by_status_found(self):
        """Test retrieving reservations with specific status."""
        mock_db = MagicMock(spec=Session)

        mock_res1 = MagicMock(spec=Reservation)
        mock_res1.id = 1
        mock_res1.vin = "VIN1"
        mock_res1.model = "Model 3"
        mock_res1.status = "IN_TRANSIT"
        mock_res1.eta_start = datetime.utcnow()
        mock_res1.eta_end = datetime.utcnow()
        mock_res1.delivery_date = None

        mock_res2 = MagicMock(spec=Reservation)
        mock_res2.id = 2
        mock_res2.vin = "VIN2"
        mock_res2.model = "Model S"
        mock_res2.status = "IN_TRANSIT"
        mock_res2.eta_start = datetime.utcnow()
        mock_res2.eta_end = datetime.utcnow()
        mock_res2.delivery_date = None

        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_res1,
            mock_res2,
        ]

        collector = ShippingCollector(db=mock_db)
        results = collector.get_reservations_by_status("IN_TRANSIT")

        assert len(results) == 2
        assert all(r["status"] == "IN_TRANSIT" for r in results)

    def test_get_reservations_by_status_empty(self):
        """Test retrieving reservations when none exist with status."""
        mock_db = MagicMock(spec=Session)
        mock_db.query.return_value.filter.return_value.all.return_value = []

        collector = ShippingCollector(db=mock_db)
        results = collector.get_reservations_by_status("CANCELLED")

        assert results == []

    def test_get_reservations_by_status_invalid(self):
        """Test handling of invalid status."""
        mock_db = MagicMock(spec=Session)
        collector = ShippingCollector(db=mock_db)
        results = collector.get_reservations_by_status("INVALID_STATUS")

        assert results == []


class TestShippingCollectorSessionManagement:
    """Tests for session management."""

    def test_collector_with_provided_session(self):
        """Test that collector uses provided session."""
        mock_db = MagicMock(spec=Session)
        collector = ShippingCollector(db=mock_db)

        assert collector.db is mock_db
        assert collector.is_managed_session is False

    @patch("app.collectors.shipping.SessionLocal")
    def test_collector_creates_session_if_none_provided(self, mock_session_local):
        """Test that collector creates SessionLocal if none provided."""
        mock_session = MagicMock(spec=Session)
        mock_session_local.return_value = mock_session

        collector = ShippingCollector()

        assert collector.is_managed_session is True

    def test_collector_cleanup(self):
        """Test that collector cleans up session."""
        mock_db = MagicMock(spec=Session)
        collector = ShippingCollector(db=mock_db)
        collector.is_managed_session = True

        collector.__del__()

        assert mock_db.close.called


class TestShippingCollectorValidStatuses:
    """Tests for valid status definitions."""

    def test_valid_statuses_defined(self):
        """Test that valid statuses are properly defined."""
        collector = ShippingCollector(db=MagicMock(spec=Session))

        assert isinstance(collector.VALID_STATUSES, list)
        assert len(collector.VALID_STATUSES) > 0
        assert "DELIVERED" in collector.VALID_STATUSES
        assert "RESERVED" in collector.VALID_STATUSES

    def test_status_progression_defined(self):
        """Test that status progression is properly defined."""
        collector = ShippingCollector(db=MagicMock(spec=Session))

        assert isinstance(collector.STATUS_PROGRESSION, list)
        assert len(collector.STATUS_PROGRESSION) > 0
        assert collector.STATUS_PROGRESSION[0] == "RESERVED"
        assert collector.STATUS_PROGRESSION[-1] == "DELIVERED"


class TestShippingCollectorIntegration:
    """Integration tests for ShippingCollector."""

    def test_get_tracking_updates_then_update_reservations(self):
        """Test complete workflow: fetch tracking then update reservations."""
        mock_db = MagicMock(spec=Session)
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.status = "CONFIRMED"
        mock_reservation.vin = "5TDJVRF33LS123456"
        mock_reservation.eta_start = None
        mock_reservation.eta_end = None

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_reservation
        )

        collector = ShippingCollector(db=mock_db)

        # Get tracking updates
        updates = collector.get_tracking_updates()
        assert len(updates) > 0

        # Update reservations using those updates
        result = collector.update_reservations(tracking_updates=updates)

        assert result["updated_count"] >= 0
        assert isinstance(result["failed_vins"], list)
        assert isinstance(result["errors"], list)
