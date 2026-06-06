from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List

from app.database.database import get_db, engine
from app.database.models import Base, Reservation
from app.database.schemas import ReservationCreate, ReservationUpdate, ReservationResponse
from app.core.config import get_settings

# Create tables on startup
Base.metadata.create_all(bind=engine)

settings = get_settings()

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="API for tracking Tesla vehicle reservations and deliveries"
)


@app.get("/", tags=["Health"])
def root():
    """Root endpoint"""
    return {
        "app": "Tesla Tracker",
        "status": "running",
        "version": settings.API_VERSION
    }


@app.get("/health", tags=["Health"])
def health():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


# ============================================================================
# RESERVATIONS CRUD
# ============================================================================

@app.get("/api/v1/reservations", response_model=List[ReservationResponse], tags=["Reservations"])
def get_reservations(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    """Get all reservations with optional filters"""
    query = db.query(Reservation)
    
    if status:
        query = query.filter(Reservation.status == status.upper())
    if model:
        query = query.filter(Reservation.model.ilike(f"%{model}%"))
    
    reservations = query.offset(skip).limit(limit).all()
    return reservations


@app.get("/api/v1/reservations/{reservation_id}", response_model=ReservationResponse, tags=["Reservations"])
def get_reservation(reservation_id: int, db: Session = Depends(get_db)):
    """Get a specific reservation by ID"""
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    return reservation


@app.post("/api/v1/reservations", response_model=ReservationResponse, status_code=201, tags=["Reservations"])
def create_reservation(
    reservation: ReservationCreate,
    db: Session = Depends(get_db)
):
    """Create a new reservation"""
    
    # Check if VIN is already registered
    if reservation.vin:
        existing = db.query(Reservation).filter(Reservation.vin == reservation.vin).first()
        if existing:
            raise HTTPException(status_code=400, detail="VIN already exists")
    
    db_reservation = Reservation(**reservation.dict())
    db.add(db_reservation)
    db.commit()
    db.refresh(db_reservation)
    
    return db_reservation


@app.put("/api/v1/reservations/{reservation_id}", response_model=ReservationResponse, tags=["Reservations"])
def update_reservation(
    reservation_id: int,
    reservation_update: ReservationUpdate,
    db: Session = Depends(get_db)
):
    """Update a reservation"""
    db_reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    
    if not db_reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    update_data = reservation_update.dict(exclude_unset=True)
    update_data['updated_at'] = datetime.utcnow()
    
    for field, value in update_data.items():
        setattr(db_reservation, field, value)
    
    db.add(db_reservation)
    db.commit()
    db.refresh(db_reservation)
    
    return db_reservation


@app.delete("/api/v1/reservations/{reservation_id}", status_code=204, tags=["Reservations"])
def delete_reservation(reservation_id: int, db: Session = Depends(get_db)):
    """Delete a reservation"""
    db_reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    
    if not db_reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    db.delete(db_reservation)
    db.commit()
    
    return None


# ============================================================================
# ANALYTICS
# ============================================================================

@app.get("/api/v1/stats", tags=["Analytics"])
def get_stats(db: Session = Depends(get_db)):
    """Get reservation statistics"""
    total = db.query(Reservation).count()
    
    by_status = {}
    for status in ["RESERVED", "BOOKED", "PENDING_VIN", "IN_TRANSIT", "DELIVERED"]:
        count = db.query(Reservation).filter(Reservation.status == status).count()
        by_status[status] = count
    
    by_model = {}
    for model in db.query(Reservation.model).distinct():
        count = db.query(Reservation).filter(Reservation.model == model[0]).count()
        by_model[model[0]] = count
    
    return {
        "total": total,
        "by_status": by_status,
        "by_model": by_model,
        "timestamp": datetime.utcnow()
    }
