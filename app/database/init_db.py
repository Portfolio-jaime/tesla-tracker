from datetime import datetime, timedelta
from app.database.models import Base, Reservation
from app.database.database import engine, SessionLocal

def init_db():
    """Initialize database with tables and seed data"""
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")
    
    # Create seed data
    db = SessionLocal()
    
    try:
        # Check if data already exists
        existing = db.query(Reservation).first()
        if existing:
            print("⚠️  Database already has data, skipping seed")
            return
        
        # Sample reservation data
        reservations = [
            Reservation(
                model="Model 3",
                color="Solid Black",
                wheels="18\" Aero",
                status="BOOKED",
                order_date=datetime.utcnow() - timedelta(days=60),
                eta_start=datetime.utcnow() + timedelta(days=30),
                eta_end=datetime.utcnow() + timedelta(days=45),
                vin="5YJ3E1EA1KF123456",
                notes="Pending VIN assignment"
            ),
            Reservation(
                model="Model Y",
                color="Pearl White Multi-Coat",
                wheels="19\" Uberturbine",
                status="PENDING_VIN",
                order_date=datetime.utcnow() - timedelta(days=45),
                eta_start=datetime.utcnow() + timedelta(days=15),
                eta_end=datetime.utcnow() + timedelta(days=30),
                notes="Awaiting VIN"
            ),
            Reservation(
                model="Model S",
                color="Midnight Silver",
                wheels="20\" Überturbine",
                status="IN_TRANSIT",
                order_date=datetime.utcnow() - timedelta(days=90),
                eta_start=datetime.utcnow() + timedelta(days=5),
                eta_end=datetime.utcnow() + timedelta(days=10),
                vin="5SAYGDEE7RL123456",
                notes="On way to delivery center"
            ),
            Reservation(
                model="Model X",
                color="Solid Black",
                wheels="20\" Überturbine",
                status="DELIVERED",
                order_date=datetime.utcnow() - timedelta(days=120),
                delivery_date=datetime.utcnow() - timedelta(days=10),
                vin="5TFJZRSH8LL123456",
                notes="Successfully delivered"
            ),
        ]
        
        db.add_all(reservations)
        db.commit()
        print(f"✅ Created {len(reservations)} sample reservations")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating seed data: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
