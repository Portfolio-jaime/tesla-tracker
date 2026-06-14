from contextlib import asynccontextmanager
import os
import re
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional, List, get_args

from app.database.database import get_db, engine
from app.database.models import Base, Reservation, PurchaseStep, STEP_KEYS
from app.database.schemas import (
    ReservationCreate, ReservationUpdate, ReservationResponse, ReservationStatus,
    PurchaseStepResponse, PurchaseStepUpdate,
)
from app.core.config import get_settings

settings = get_settings()

VALID_STATUSES = list(get_args(ReservationStatus))


def _ensure_steps(reservation_id: int, db: Session) -> list:
    existing = (
        db.query(PurchaseStep)
        .filter(PurchaseStep.reservation_id == reservation_id)
        .all()
    )
    existing_keys = {s.step_key for s in existing}
    added = False
    for i, key in enumerate(STEP_KEYS, start=1):
        if key not in existing_keys:
            db.add(PurchaseStep(
                reservation_id=reservation_id,
                step_order=i,
                step_key=key,
                completed=False,
            ))
            added = True
    if added:
        db.commit()
    return (
        db.query(PurchaseStep)
        .filter(PurchaseStep.reservation_id == reservation_id)
        .order_by(PurchaseStep.step_order)
        .all()
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = settings.DATABASE_URL
    # Extract file path from sqlite URL (sqlite:///./path or sqlite:////abs/path)
    match = re.match(r"sqlite:///(.+)", db_url)
    if match:
        db_path = match.group(1)
        db_dir = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(db_dir, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="API for tracking Tesla vehicle reservations and deliveries",
    lifespan=lifespan,
)


@app.get("/", tags=["Health"])
def root():
    return {"app": "Tesla Tracker", "status": "running", "version": settings.API_VERSION}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}


@app.get("/api/v1/reservations", response_model=List[ReservationResponse], tags=["Reservations"])
def get_reservations(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    query = db.query(Reservation)
    if status:
        query = query.filter(Reservation.status == status.upper())
    if model:
        query = query.filter(Reservation.model.ilike(f"%{model}%"))
    return query.offset(skip).limit(limit).all()


@app.get("/api/v1/reservations/{reservation_id}", response_model=ReservationResponse, tags=["Reservations"])
def get_reservation(reservation_id: int, db: Session = Depends(get_db)):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return reservation


@app.post("/api/v1/reservations", response_model=ReservationResponse, status_code=201, tags=["Reservations"])
def create_reservation(reservation: ReservationCreate, db: Session = Depends(get_db)):
    if reservation.vin:
        existing = db.query(Reservation).filter(Reservation.vin == reservation.vin).first()
        if existing:
            raise HTTPException(status_code=400, detail="VIN already exists")
    db_reservation = Reservation(**reservation.model_dump())
    db.add(db_reservation)
    db.commit()
    db.refresh(db_reservation)
    return db_reservation


@app.put("/api/v1/reservations/{reservation_id}", response_model=ReservationResponse, tags=["Reservations"])
def update_reservation(reservation_id: int, reservation_update: ReservationUpdate, db: Session = Depends(get_db)):
    db_reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not db_reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    update_data = reservation_update.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)
    for field, value in update_data.items():
        setattr(db_reservation, field, value)
    db.add(db_reservation)
    db.commit()
    db.refresh(db_reservation)
    return db_reservation


@app.delete("/api/v1/reservations/{reservation_id}", status_code=204, tags=["Reservations"])
def delete_reservation(reservation_id: int, db: Session = Depends(get_db)):
    db_reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not db_reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    db.delete(db_reservation)
    db.commit()
    return None


@app.get(
    "/api/v1/reservations/{reservation_id}/steps",
    response_model=List[PurchaseStepResponse],
    tags=["Steps"],
)
def get_steps(reservation_id: int, db: Session = Depends(get_db)):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return _ensure_steps(reservation_id, db)


@app.patch(
    "/api/v1/reservations/{reservation_id}/steps/{step_key}",
    response_model=PurchaseStepResponse,
    tags=["Steps"],
)
def update_step(
    reservation_id: int,
    step_key: str,
    update: PurchaseStepUpdate,
    db: Session = Depends(get_db),
):
    if step_key not in STEP_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step_key. Must be one of: {STEP_KEYS}",
        )
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    _ensure_steps(reservation_id, db)
    step = (
        db.query(PurchaseStep)
        .filter(
            PurchaseStep.reservation_id == reservation_id,
            PurchaseStep.step_key == step_key,
        )
        .first()
    )
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")
    update_data = update.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)
    for field, value in update_data.items():
        setattr(step, field, value)
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


@app.get("/api/v1/stats", tags=["Analytics"])
def get_stats(db: Session = Depends(get_db)):
    total = db.query(Reservation).count()
    by_status = {s: db.query(Reservation).filter(Reservation.status == s).count() for s in VALID_STATUSES}
    by_model = {}
    for (model,) in db.query(Reservation.model).distinct():
        by_model[model] = db.query(Reservation).filter(Reservation.model == model).count()
    return {"total": total, "by_status": by_status, "by_model": by_model, "timestamp": datetime.now(timezone.utc)}
