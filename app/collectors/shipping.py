"""
Shipping collector for Tesla Tracker.
Handles tracking updates and reservation status management.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database.database import SessionLocal
from app.database.models import Reservation
from app.alerts.telegram import TelegramAlert
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ShippingCollector:
    """Collector for managing shipping and delivery tracking of reservations."""

    # Possible status transitions
    VALID_STATUSES = [
        "RESERVED",
        "CONFIRMED",
        "MANUFACTURING",
        "QUALITY_CHECK",
        "SHIPPING",
        "IN_TRANSIT",
        "DELIVERED",
        "CANCELLED",
    ]

    # Simulated status progression
    STATUS_PROGRESSION = [
        "RESERVED",
        "CONFIRMED",
        "MANUFACTURING",
        "QUALITY_CHECK",
        "SHIPPING",
        "IN_TRANSIT",
        "DELIVERED",
    ]

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize the ShippingCollector.

        Args:
            db: SQLAlchemy session. If None, creates a new SessionLocal.
        """
        self.db = db or SessionLocal()
        self.is_managed_session = db is None
        _settings = get_settings()
        self._alert = TelegramAlert(
            token=_settings.TELEGRAM_BOT_TOKEN,
            chat_id=_settings.TELEGRAM_CHAT_ID,
        )

    def __del__(self):
        """Clean up session if it was created by this instance."""
        if self.is_managed_session and self.db:
            self.db.close()

    def get_tracking_updates(self, vin: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Simulate fetching tracking updates from external API or service.

        This method returns simulated tracking data that would normally
        come from a shipping provider API.

        Args:
            vin: Optional VIN to filter tracking updates. If None, returns all.

        Returns:
            List of tracking update dictionaries with simulated data.

        Raises:
            Exception: If there's an error retrieving tracking data.
        """
        try:
            logger.info(f"Fetching tracking updates for VIN: {vin or 'ALL'}")

            # Simulated tracking data from external source
            mock_tracking_data = [
                {
                    "vin": "5TDJVRF33LS123456",
                    "status": "IN_TRANSIT",
                    "eta_start": datetime.utcnow() + timedelta(days=2),
                    "eta_end": datetime.utcnow() + timedelta(days=5),
                    "current_location": "Chicago, IL",
                    "timestamp": datetime.utcnow(),
                },
                {
                    "vin": "5TDJVRF33LS123457",
                    "status": "QUALITY_CHECK",
                    "eta_start": datetime.utcnow() + timedelta(days=1),
                    "eta_end": datetime.utcnow() + timedelta(days=3),
                    "current_location": "Factory QC",
                    "timestamp": datetime.utcnow(),
                },
                {
                    "vin": "5TDJVRF33LS123458",
                    "status": "MANUFACTURING",
                    "eta_start": datetime.utcnow() + timedelta(days=5),
                    "eta_end": datetime.utcnow() + timedelta(days=15),
                    "current_location": "Fremont Factory",
                    "timestamp": datetime.utcnow(),
                },
            ]

            # Filter by VIN if provided
            if vin:
                updates = [u for u in mock_tracking_data if u["vin"] == vin]
                if not updates:
                    logger.warning(f"No tracking data found for VIN: {vin}")
                    return []
                return updates

            logger.info(f"Retrieved {len(mock_tracking_data)} tracking updates")
            return mock_tracking_data

        except Exception as e:
            logger.error(f"Error fetching tracking updates: {str(e)}")
            raise

    def update_reservations(
        self, tracking_updates: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Update reservations based on tracking data.

        This method processes tracking updates and updates the corresponding
        reservations in the database with new status and ETA information.

        Args:
            tracking_updates: List of tracking update dictionaries.
                            If None, fetches fresh updates.

        Returns:
            Dictionary with statistics about the update operation:
                - updated_count: Number of reservations updated
                - failed_vins: List of VINs that failed to update
                - errors: List of error messages

        Raises:
            SQLAlchemyError: If there's a database transaction error.
        """
        try:
            # Fetch fresh updates if not provided
            if tracking_updates is None:
                tracking_updates = self.get_tracking_updates()

            logger.info(f"Processing {len(tracking_updates)} tracking updates")

            updated_count = 0
            failed_vins = []
            errors = []

            # Process each tracking update
            for update in tracking_updates:
                try:
                    vin = update.get("vin")
                    if not vin:
                        error_msg = "Tracking update missing VIN field"
                        logger.warning(error_msg)
                        errors.append(error_msg)
                        continue

                    # Find reservation by VIN
                    reservation = self.db.query(Reservation).filter(
                        Reservation.vin == vin
                    ).first()

                    if not reservation:
                        error_msg = f"Reservation not found for VIN: {vin}"
                        logger.warning(error_msg)
                        failed_vins.append(vin)
                        errors.append(error_msg)
                        continue

                    # Store old status for logging
                    old_status = reservation.status

                    # Update reservation fields
                    new_status = update.get("status", reservation.status)

                    # Validate status
                    if new_status not in self.VALID_STATUSES:
                        logger.warning(
                            f"Invalid status '{new_status}' for VIN {vin}. "
                            f"Valid options: {self.VALID_STATUSES}"
                        )
                        new_status = old_status

                    reservation.status = new_status
                    if new_status != old_status:
                        self._alert.send(
                            model=reservation.model,
                            vin=reservation.vin or "",
                            old_status=old_status,
                            new_status=new_status,
                        )
                    reservation.eta_start = update.get(
                        "eta_start", reservation.eta_start
                    )
                    reservation.eta_end = update.get("eta_end", reservation.eta_end)

                    # Set delivery_date if status is DELIVERED
                    if new_status == "DELIVERED":
                        reservation.delivery_date = datetime.utcnow()

                    # Update metadata
                    reservation.updated_at = datetime.utcnow()

                    # Log the update
                    logger.info(
                        f"Updated reservation VIN={vin}: "
                        f"{old_status} -> {new_status}, "
                        f"ETA: {reservation.eta_start} to {reservation.eta_end}"
                    )

                    updated_count += 1

                except Exception as e:
                    error_msg = f"Error updating VIN {update.get('vin', 'UNKNOWN')}: {str(e)}"
                    logger.error(error_msg)
                    failed_vins.append(update.get("vin", "UNKNOWN"))
                    errors.append(error_msg)
                    continue

            # Commit transaction
            try:
                self.db.commit()
                logger.info(
                    f"Successfully committed {updated_count} reservation updates"
                )
            except SQLAlchemyError as e:
                self.db.rollback()
                logger.error(f"Database commit failed, rolled back changes: {str(e)}")
                raise

            return {
                "updated_count": updated_count,
                "failed_vins": failed_vins,
                "errors": errors,
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error during update_reservations: {str(e)}")
            self.db.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error during update_reservations: {str(e)}")
            raise

    def get_reservation_status(self, vin: str) -> Optional[Dict[str, Any]]:
        """
        Get the current status of a reservation by VIN.

        Args:
            vin: Vehicle Identification Number

        Returns:
            Dictionary with reservation status info, or None if not found.
        """
        try:
            reservation = self.db.query(Reservation).filter(
                Reservation.vin == vin
            ).first()

            if not reservation:
                logger.warning(f"Reservation not found for VIN: {vin}")
                return None

            return {
                "id": reservation.id,
                "vin": reservation.vin,
                "model": reservation.model,
                "status": reservation.status,
                "eta_start": reservation.eta_start,
                "eta_end": reservation.eta_end,
                "delivery_date": reservation.delivery_date,
                "order_date": reservation.order_date,
            }

        except Exception as e:
            logger.error(f"Error retrieving reservation status for VIN {vin}: {str(e)}")
            raise

    def advance_reservation_status(self, vin: str) -> Optional[Dict[str, Any]]:
        """
        Advance a reservation to the next status in the progression.

        This is useful for testing and development purposes.

        Args:
            vin: Vehicle Identification Number

        Returns:
            Updated reservation info, or None if not found.

        Raises:
            ValueError: If the reservation is at the final status.
        """
        try:
            reservation = self.db.query(Reservation).filter(
                Reservation.vin == vin
            ).first()

            if not reservation:
                logger.warning(f"Reservation not found for VIN: {vin}")
                return None

            current_status = reservation.status
            current_index = (
                self.STATUS_PROGRESSION.index(current_status)
                if current_status in self.STATUS_PROGRESSION
                else 0
            )

            if current_index >= len(self.STATUS_PROGRESSION) - 1:
                logger.warning(
                    f"Reservation VIN {vin} is already at final status: {current_status}"
                )
                raise ValueError(
                    f"Cannot advance from final status: {current_status}"
                )

            new_status = self.STATUS_PROGRESSION[current_index + 1]
            old_status = reservation.status

            reservation.status = new_status
            reservation.updated_at = datetime.utcnow()

            if new_status == "DELIVERED":
                reservation.delivery_date = datetime.utcnow()

            self.db.commit()

            logger.info(
                f"Advanced reservation VIN={vin} from {old_status} to {new_status}"
            )

            return self.get_reservation_status(vin)

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Database error advancing status for VIN {vin}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error advancing status for VIN {vin}: {str(e)}")
            raise

    def get_reservations_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Get all reservations with a specific status.

        Args:
            status: The status to filter by.

        Returns:
            List of reservation dictionaries.
        """
        try:
            if status not in self.VALID_STATUSES:
                logger.warning(
                    f"Invalid status '{status}'. Valid options: {self.VALID_STATUSES}"
                )
                return []

            reservations = self.db.query(Reservation).filter(
                Reservation.status == status
            ).all()

            logger.info(f"Found {len(reservations)} reservations with status {status}")

            return [
                {
                    "id": r.id,
                    "vin": r.vin,
                    "model": r.model,
                    "status": r.status,
                    "eta_start": r.eta_start,
                    "eta_end": r.eta_end,
                    "delivery_date": r.delivery_date,
                }
                for r in reservations
            ]

        except Exception as e:
            logger.error(f"Error retrieving reservations by status {status}: {str(e)}")
            raise
