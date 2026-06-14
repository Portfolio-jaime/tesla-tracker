from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from typing import Literal, Optional

ReservationStatus = Literal[
    "RESERVED", "CONFIRMED", "MANUFACTURING", "QUALITY_CHECK",
    "SHIPPING", "IN_TRANSIT", "DELIVERED", "CANCELLED",
]


class ReservationBase(BaseModel):
    model: str = Field(..., min_length=1, max_length=50)
    color: Optional[str] = Field(None, max_length=50)
    wheels: Optional[str] = Field(None, max_length=50)
    status: ReservationStatus = "RESERVED"
    order_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    eta_start: Optional[datetime] = None
    eta_end: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    vin: Optional[str] = Field(None, max_length=17)
    notes: Optional[str] = None


class ReservationCreate(ReservationBase):
    pass


class ReservationUpdate(BaseModel):
    model: Optional[str] = None
    color: Optional[str] = None
    wheels: Optional[str] = None
    status: Optional[ReservationStatus] = None
    eta_start: Optional[datetime] = None
    eta_end: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    vin: Optional[str] = None
    notes: Optional[str] = None


class ReservationResponse(ReservationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# --- Purchase Steps ---

class PurchaseStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reservation_id: int
    step_order: int
    step_key: str
    completed: bool
    completed_date: Optional[datetime] = None
    notes: Optional[str] = None
    updated_at: datetime


class PurchaseStepUpdate(BaseModel):
    completed: Optional[bool] = None
    completed_date: Optional[datetime] = None
    notes: Optional[str] = None
