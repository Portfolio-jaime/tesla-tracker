from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    Index, ForeignKey, UniqueConstraint,
)
from datetime import datetime


STEP_KEYS = [
    "RESERVA",
    "CONFIRMACION",
    "PRODUCCION",
    "ENVIO_MARITIMO",
    "ADUANA",
    "ENTREGA",
]

STEP_LABELS = {
    "RESERVA": "Reserva",
    "CONFIRMACION": "Confirmación de orden",
    "PRODUCCION": "Producción",
    "ENVIO_MARITIMO": "Envío marítimo",
    "ADUANA": "Aduana Colombia",
    "ENTREGA": "Entrega",
}


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
    model = Column(String(50), nullable=False)
    color = Column(String(50))
    wheels = Column(String(50))
    status = Column(String(50), nullable=False, default="RESERVED")
    order_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    eta_start = Column(DateTime)
    eta_end = Column(DateTime)
    delivery_date = Column(DateTime)
    vin = Column(String(17), unique=True, index=True)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    steps = relationship("PurchaseStep", back_populates="reservation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Reservation(id={self.id}, model={self.model}, status={self.status}, vin={self.vin})>"


class PurchaseStep(Base):
    __tablename__ = "purchase_steps"
    __table_args__ = (
        UniqueConstraint("reservation_id", "step_order", name="uq_res_step_order"),
        UniqueConstraint("reservation_id", "step_key", name="uq_res_step_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    step_key = Column(String(50), nullable=False)
    completed = Column(Boolean, nullable=False, default=False)
    completed_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    reservation = relationship("Reservation", back_populates="steps")

    def __repr__(self):
        return f"<PurchaseStep(reservation_id={self.reservation_id}, step_key={self.step_key}, completed={self.completed})>"
