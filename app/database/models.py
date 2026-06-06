from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        Index('idx_status', 'status'),
        Index('idx_order_date', 'order_date'),
        Index('idx_vin', 'vin'),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Vehicle Info
    model = Column(String(50), nullable=False)
    color = Column(String(50))
    wheels = Column(String(50))
    
    # Status
    status = Column(String(50), nullable=False, default="RESERVED")
    
    # Dates
    order_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    eta_start = Column(DateTime)
    eta_end = Column(DateTime)
    delivery_date = Column(DateTime)
    
    # Vehicle Identification
    vin = Column(String(17), unique=True, index=True)
    
    # Additional Info
    notes = Column(Text)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Reservation(id={self.id}, model={self.model}, status={self.status}, vin={self.vin})>"
