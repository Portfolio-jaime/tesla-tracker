from datetime import datetime, timedelta, timezone
from app.database.models import Base, Reservation
from app.database.database import engine, SessionLocal


def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")

    db = SessionLocal()
    try:
        if db.query(Reservation).first():
            print("⚠️  Database already has data, skipping seed")
            return

        reservations = [
            Reservation(
                model="Model 3",
                color="Solid Black",
                wheels='18" Aero',
                status="CONFIRMED",
                order_date=datetime.now(timezone.utc) - timedelta(days=60),
                eta_start=datetime.now(timezone.utc) + timedelta(days=30),
                eta_end=datetime.now(timezone.utc) + timedelta(days=45),
                vin="5YJ3E1EA1KF123456",
                notes="Configuración premium",
            ),
            Reservation(
                model="Model Y",
                color="Pearl White Multi-Coat",
                wheels='19" Uberturbine',
                status="MANUFACTURING",
                order_date=datetime.now(timezone.utc) - timedelta(days=45),
                eta_start=datetime.now(timezone.utc) + timedelta(days=15),
                eta_end=datetime.now(timezone.utc) + timedelta(days=30),
                notes="7 asientos",
            ),
            Reservation(
                model="Model S",
                color="Midnight Silver",
                wheels='20" Überturbine',
                status="IN_TRANSIT",
                order_date=datetime.now(timezone.utc) - timedelta(days=90),
                eta_start=datetime.now(timezone.utc) + timedelta(days=5),
                eta_end=datetime.now(timezone.utc) + timedelta(days=10),
                vin="5SAYGDEE7RL123456",
                notes="En camino al centro de entrega",
            ),
            Reservation(
                model="Model X",
                color="Solid Black",
                wheels='20" Überturbine',
                status="DELIVERED",
                order_date=datetime.now(timezone.utc) - timedelta(days=120),
                delivery_date=datetime.now(timezone.utc) - timedelta(days=10),
                vin="5TFJZRSH8LL123456",
                notes="Entregado exitosamente",
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
