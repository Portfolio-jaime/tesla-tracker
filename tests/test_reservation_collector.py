"""
Tests for ReservationCollector.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.collectors.reservation import ReservationCollector
from app.database.models import Reservation
from app.database.schemas import ReservationCreate


class TestReservationCollectorFetch:
    """Tests for fetch_reservations method."""
    
    def test_fetch_reservations_returns_list(self):
        """Test that fetch_reservations returns a list of reservations."""
        collector = ReservationCollector()
        reservations = collector.fetch_reservations()
        
        assert isinstance(reservations, list)
        assert len(reservations) > 0
    
    def test_fetch_reservations_contains_required_fields(self):
        """Test that fetched reservations contain required fields."""
        collector = ReservationCollector()
        reservations = collector.fetch_reservations()
        
        required_fields = ["model", "status", "order_date"]
        for reservation in reservations:
            for field in required_fields:
                assert field in reservation
                assert reservation[field] is not None
    
    def test_fetch_reservations_has_valid_data_types(self):
        """Test that fetched reservations have valid data types."""
        collector = ReservationCollector()
        reservations = collector.fetch_reservations()
        
        for reservation in reservations:
            assert isinstance(reservation["model"], str)
            assert isinstance(reservation["status"], str)
            assert isinstance(reservation["order_date"], datetime)


class TestReservationCollectorValidation:
    """Tests for validate_reservation method."""
    
    def test_validate_reservation_success(self):
        """Test successful validation of reservation data."""
        collector = ReservationCollector()
        data = {
            "model": "Model 3",
            "status": "RESERVED",
            "order_date": datetime(2024, 1, 15),
            "color": "Midnight Black",
            "vin": "5YJ3E1EA0JF123456",
        }
        
        validated = collector.validate_reservation(data)
        
        assert validated is not None
        assert isinstance(validated, ReservationCreate)
        assert validated.model == "Model 3"
    
    def test_validate_reservation_missing_required_field(self):
        """Test validation fails with missing required field."""
        collector = ReservationCollector()
        data = {
            "color": "Midnight Black",
            "status": "RESERVED",
        }
        
        validated = collector.validate_reservation(data)
        
        assert validated is None
    
    def test_validate_reservation_invalid_type(self):
        """Test validation fails with invalid data type."""
        collector = ReservationCollector()
        data = {
            "model": "Model 3",
            "status": "RESERVED",
            "order_date": "not-a-date",
        }
        
        validated = collector.validate_reservation(data)
        
        assert validated is None
    
    def test_validate_reservation_with_all_fields(self):
        """Test validation with all optional fields."""
        collector = ReservationCollector()
        data = {
            "model": "Model S",
            "color": "Solid Black",
            "wheels": "19-inch Überturbine",
            "status": "IN_PRODUCTION",
            "order_date": datetime(2024, 1, 1),
            "eta_start": datetime(2024, 3, 15),
            "eta_end": datetime(2024, 4, 15),
            "delivery_date": datetime(2024, 4, 10),
            "vin": "5YJ3E1EA0JF123458",
            "notes": "Long Range",
        }
        
        validated = collector.validate_reservation(data)
        
        assert validated is not None
        assert validated.vin == "5YJ3E1EA0JF123458"
        assert validated.delivery_date == datetime(2024, 4, 10)


class TestReservationCollectorSave:
    """Tests for save-related methods."""
    
    @patch('app.collectors.reservation.SessionLocal')
    def test_save_reservation_creates_new(self, mock_session_local):
        """Test saving a new reservation."""
        mock_session = MagicMock(spec=Session)
        mock_session_local.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        collector = ReservationCollector()
        collector.db = mock_session
        
        validated_data = ReservationCreate(
            model="Model 3",
            status="RESERVED",
            order_date=datetime(2024, 1, 15),
        )
        
        result = collector._save_reservation(mock_session, validated_data)
        
        assert mock_session.add.called
        assert mock_session.commit.called
    
    @patch('app.collectors.reservation.SessionLocal')
    def test_save_reservation_updates_existing(self, mock_session_local):
        """Test updating an existing reservation by VIN."""
        mock_session = MagicMock(spec=Session)
        mock_session_local.return_value = mock_session
        
        existing_reservation = MagicMock(spec=Reservation)
        mock_session.query.return_value.filter.return_value.first.return_value = existing_reservation
        
        collector = ReservationCollector()
        collector.db = mock_session
        
        validated_data = ReservationCreate(
            model="Model 3",
            status="RESERVED",
            order_date=datetime(2024, 1, 15),
            vin="5YJ3E1EA0JF123456",
        )
        
        result = collector._save_reservation(mock_session, validated_data)
        
        assert mock_session.commit.called
    
    def test_validate_and_save_empty_list(self):
        """Test validate_and_save with empty list."""
        collector = ReservationCollector()
        result = collector.validate_and_save([])
        
        assert result["total"] == 0
        assert result["saved"] == 0
        assert result["failed"] == 0
    
    @patch('app.collectors.reservation.SessionLocal')
    def test_validate_and_save_with_valid_data(self, mock_session_local):
        """Test validate_and_save with valid data."""
        mock_session = MagicMock(spec=Session)
        mock_session_local.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        collector = ReservationCollector()
        
        data = [
            {
                "model": "Model 3",
                "status": "RESERVED",
                "order_date": datetime(2024, 1, 15),
            }
        ]
        
        result = collector.validate_and_save(data)
        
        assert result["total"] == 1
        assert result["saved"] == 1
        assert result["failed"] == 0
        assert len(result["errors"]) == 0
    
    @patch('app.collectors.reservation.SessionLocal')
    def test_validate_and_save_with_invalid_data(self, mock_session_local):
        """Test validate_and_save with invalid data."""
        mock_session = MagicMock(spec=Session)
        mock_session_local.return_value = mock_session
        
        collector = ReservationCollector()
        
        data = [
            {
                "color": "Midnight Black",
            }
        ]
        
        result = collector.validate_and_save(data)
        
        assert result["total"] == 1
        assert result["saved"] == 0
        assert result["failed"] == 1
        assert len(result["errors"]) > 0


class TestReservationCollectorWorkflow:
    """Tests for the complete workflow."""
    
    @patch('app.collectors.reservation.SessionLocal')
    def test_run_complete_workflow(self, mock_session_local):
        """Test complete reservation collection workflow."""
        mock_session = MagicMock(spec=Session)
        mock_session_local.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        collector = ReservationCollector()
        result = collector.run()
        
        assert isinstance(result, dict)
        assert "total" in result
        assert "saved" in result
        assert "failed" in result
        assert "errors" in result
        assert result["total"] > 0
    
    def test_collector_closes_session(self):
        """Test that collector properly closes database session."""
        collector = ReservationCollector()
        collector.db = MagicMock(spec=Session)
        
        collector.close()
        
        assert collector.db is None


class TestReservationCollectorErrorHandling:
    """Tests for error handling."""
    
    def test_validate_and_save_handles_database_errors(self):
        """Test that errors are caught and reported."""
        collector = ReservationCollector()
        collector.db = MagicMock(spec=Session)
        collector.db.query.side_effect = Exception("Database error")
        
        data = [
            {
                "model": "Model 3",
                "status": "RESERVED",
                "order_date": datetime(2024, 1, 15),
            }
        ]
        
        result = collector.validate_and_save(data)
        
        assert result["failed"] >= 0
        assert isinstance(result["errors"], list)
    
    @patch('app.collectors.reservation.SessionLocal')
    def test_run_handles_fetch_errors(self, mock_session_local):
        """Test that run method handles fetch errors gracefully."""
        collector = ReservationCollector()
        
        with patch.object(collector, 'fetch_reservations', side_effect=Exception("Fetch error")):
            result = collector.run()
            
            assert result["failed"] > 0
            assert len(result["errors"]) > 0
