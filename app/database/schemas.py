from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class ReservationBase(BaseModel):
    """Base reservation schema"""
    model: str = Field(..., min_length=1, max_length=50)
    color: Optional[str] = Field(None, max_length=50)
    wheels: Optional[str] = Field(None, max_length=50)
    status: str = Field(default="RESERVED", max_length=50)
    order_date: datetime = Field(default_factory=datetime.utcnow)
    eta_start: Optional[datetime] = None
    eta_end: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    vin: Optional[str] = Field(None, max_length=17)
    notes: Optional[str] = None


class ReservationCreate(ReservationBase):
    """Schema for creating a reservation"""
    pass


class ReservationUpdate(BaseModel):
    """Schema for updating a reservation"""
    model: Optional[str] = None
    color: Optional[str] = None
    wheels: Optional[str] = None
    status: Optional[str] = None
    eta_start: Optional[datetime] = None
    eta_end: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    vin: Optional[str] = None
    notes: Optional[str] = None


class ReservationResponse(ReservationBase):
    """Schema for reservation response"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
