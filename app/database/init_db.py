from datetime import datetime, timedelta, timezone
from app.database.models import Base, Reservation
from app.database.database import engine, SessionLocal


def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")

    print("✅ Database ready")


if __name__ == "__main__":
    init_db()
