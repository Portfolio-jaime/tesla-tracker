"""
ReservationCollector - Collects and validates Tesla reservations from external sources.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.database.models import Reservation
from app.database.schemas import ReservationCreate
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ReservationCollector:
    """
    Collector for Tesla reservations.
    
    Simulates fetching reservation data from an external source (API, CSV, etc.),
    validates the data, and saves it to the database.
    """
    
    def __init__(self):
        """Initialize the ReservationCollector."""
        self.db: Optional[Session] = None
        self.logger = logging.getLogger(__name__)
    
    def _get_db_session(self) -> Session:
        """Get or create a database session."""
        if self.db is None:
            self.db = SessionLocal()
        return self.db
    
    def close(self) -> None:
        """Close the database session."""
        if self.db:
            self.db.close()
            self.db = None
    
    def fetch_reservations(self) -> List[Dict[str, Any]]:
        """
        Simulate fetching reservations from an external source.
        
        In a real scenario, this would:
        - Call a Tesla API
        - Read from a CSV file
        - Query another database
        - etc.
        
        Returns:
            List[Dict[str, Any]]: List of reservation data dictionaries
        """
        try:
            self.logger.info("Fetching reservations from external source...")
            settings = get_settings()

            if settings.TESLA_VIN and settings.TESLA_MODEL:
                self.logger.info("Usando datos de variables de entorno TESLA_*")
                data: Dict[str, Any] = {
                    "model": settings.TESLA_MODEL,
                    "status": settings.TESLA_STATUS or "RESERVED",
                    "vin": settings.TESLA_VIN,
                }
                if settings.TESLA_COLOR:
                    data["color"] = settings.TESLA_COLOR
                if settings.TESLA_ETA_START:
                    data["eta_start"] = datetime.fromisoformat(settings.TESLA_ETA_START)
                if settings.TESLA_ETA_END:
                    data["eta_end"] = datetime.fromisoformat(settings.TESLA_ETA_END)
                return [data]

            self.logger.info("TESLA_VIN no configurado — usando datos de ejemplo")
            return [
                {
                    "model": "Model 3",
                    "color": "Midnight Black",
                    "wheels": "18-inch Aero",
                    "status": "CONFIRMED",
                    "order_date": datetime(2024, 1, 15),
                    "eta_start": datetime(2024, 3, 1),
                    "eta_end": datetime(2024, 4, 30),
                    "vin": "5YJ3E1EA0JF123456",
                    "notes": "Premium interior, Full Self-Driving",
                },
                {
                    "model": "Model Y",
                    "color": "Pearl White",
                    "wheels": "20-inch Aero",
                    "status": "MANUFACTURING",
                    "order_date": datetime(2024, 2, 1),
                    "eta_start": datetime(2024, 4, 15),
                    "eta_end": datetime(2024, 5, 31),
                    "vin": "5YJ3E1EA0JF123457",
                    "notes": "7-seater configuration",
                },
                {
                    "model": "Model S",
                    "color": "Solid Black",
                    "wheels": "19-inch Überturbine",
                    "status": "IN_TRANSIT",
                    "order_date": datetime(2024, 1, 1),
                    "eta_start": datetime(2024, 3, 15),
                    "eta_end": datetime(2024, 4, 15),
                    "delivery_date": datetime(2024, 4, 10),
                    "vin": "5YJ3E1EA0JF123458",
                    "notes": "Long Range",
                },
            ]
        except Exception as e:
            self.logger.error(f"Error fetching reservations: {str(e)}", exc_info=True)
            raise
    
    def validate_reservation(self, data: Dict[str, Any]) -> Optional[ReservationCreate]:
        """
        Validate reservation data using the ReservationCreate schema.
        
        Args:
            data: Dictionary containing reservation data
            
        Returns:
            ReservationCreate: Validated reservation data or None if validation fails
        """
        try:
            validated_data = ReservationCreate(**data)
            self.logger.debug(f"Validated reservation for model: {validated_data.model}")
            return validated_data
            
        except ValidationError as e:
            self.logger.warning(f"Validation error for reservation: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error validating reservation: {str(e)}", exc_info=True)
            return None
    
    def _get_existing_reservation_by_vin(self, db: Session, vin: Optional[str]) -> Optional[Reservation]:
        """
        Get an existing reservation by VIN.
        
        Args:
            db: Database session
            vin: Vehicle Identification Number
            
        Returns:
            Reservation: Existing reservation or None
        """
        if not vin:
            return None
        
        try:
            return db.query(Reservation).filter(Reservation.vin == vin).first()
        except Exception as e:
            self.logger.error(f"Error querying reservation by VIN: {str(e)}", exc_info=True)
            return None
    
    def _save_reservation(self, db: Session, validated_data: ReservationCreate) -> Optional[Reservation]:
        """
        Save a validated reservation to the database.
        
        Updates existing reservation if VIN matches, otherwise creates new.
        
        Args:
            db: Database session
            validated_data: Validated reservation data
            
        Returns:
            Reservation: Saved reservation or None if save failed
        """
        try:
            # Check if reservation with this VIN already exists
            existing = self._get_existing_reservation_by_vin(db, validated_data.vin)
            
            if existing:
                # Update existing reservation
                self.logger.info(f"Updating existing reservation with VIN: {validated_data.vin}")
                for field, value in validated_data.model_dump().items():
                    setattr(existing, field, value)
                existing.updated_at = datetime.utcnow()
                db.add(existing)
                reservation = existing
            else:
                # Create new reservation
                self.logger.info(f"Creating new reservation for model: {validated_data.model}")
                reservation = Reservation(**validated_data.model_dump())
                db.add(reservation)
            
            db.commit()
            db.refresh(reservation)
            self.logger.info(f"Successfully saved reservation: {reservation}")
            return reservation
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error saving reservation to database: {str(e)}", exc_info=True)
            return None
    
    def validate_and_save(self, reservations_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate and save a list of reservations to the database.
        
        Args:
            reservations_data: List of reservation data dictionaries
            
        Returns:
            Dict containing:
                - total: Total number of reservations processed
                - saved: Number of successfully saved reservations
                - failed: Number of reservations that failed validation/save
                - errors: List of error messages
        """
        result = {
            "total": len(reservations_data),
            "saved": 0,
            "failed": 0,
            "errors": [],
        }
        
        if not reservations_data:
            self.logger.warning("No reservations to save")
            return result
        
        db = self._get_db_session()
        
        try:
            for idx, reservation_data in enumerate(reservations_data):
                try:
                    # Validate data
                    validated_data = self.validate_reservation(reservation_data)
                    if not validated_data:
                        result["failed"] += 1
                        error_msg = f"Validation failed for reservation {idx + 1}"
                        result["errors"].append(error_msg)
                        continue
                    
                    # Save to database
                    saved_reservation = self._save_reservation(db, validated_data)
                    if saved_reservation:
                        result["saved"] += 1
                    else:
                        result["failed"] += 1
                        error_msg = f"Failed to save reservation {idx + 1} to database"
                        result["errors"].append(error_msg)
                        
                except Exception as e:
                    result["failed"] += 1
                    error_msg = f"Unexpected error processing reservation {idx + 1}: {str(e)}"
                    result["errors"].append(error_msg)
                    self.logger.error(error_msg, exc_info=True)
            
            # Log summary
            self.logger.info(
                f"Reservation processing complete - "
                f"Total: {result['total']}, "
                f"Saved: {result['saved']}, "
                f"Failed: {result['failed']}"
            )
            
            return result
            
        except Exception as e:
            error_msg = f"Error during validate_and_save: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            result["errors"].append(error_msg)
            return result
    
    def run(self) -> Dict[str, Any]:
        """
        Run the full reservation collection workflow.
        
        Fetches reservations and saves them to the database.
        
        Returns:
            Dict: Result dictionary with processing statistics
        """
        try:
            self.logger.info("Starting reservation collection workflow...")
            
            # Fetch reservations from external source
            reservations_data = self.fetch_reservations()
            
            # Validate and save to database
            result = self.validate_and_save(reservations_data)
            
            self.logger.info("Reservation collection workflow completed successfully")
            return result
            
        except Exception as e:
            error_msg = f"Error in reservation collection workflow: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {
                "total": 0,
                "saved": 0,
                "failed": 1,
                "errors": [error_msg],
            }
        finally:
            self.close()
