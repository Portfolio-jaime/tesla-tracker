# 🚗 Tesla Tracker

Sistema inteligente de seguimiento de entregas Tesla. Monitorea el estado de tu reserva, predicciones de entrega y recibe alertas en tiempo real.

## ✨ Características

- 📊 **Dashboard dinámico** - Visualización en tiempo real de tu reserva
- 🔔 **Alertas** - Notificaciones vía Telegram cuando hay actualizaciones
- 🤖 **IA Predictor** - Predicción de fechas de entrega con Groq AI
- 📈 **Analytics** - Estadísticas y reportes de reservas
- 🐳 **Docker Ready** - Containerizado para fácil deployment
- ✅ **Tested** - Suite de tests con pytest

## 🛠️ Stack Técnico

| Componente | Tecnología |
|-----------|-----------|
| **Backend API** | FastAPI + SQLAlchemy |
| **Frontend Dashboard** | Streamlit |
| **Database** | SQLite (fácil de cambiar a PostgreSQL) |
| **Tests** | pytest + TestClient |
| **Containerization** | Docker + Docker Compose |
| **AI/ML** | Groq API (Mixtral) |
| **Alerts** | Telegram Bot API |

## 🚀 Quick Start

### Opción 1: Local Development

#### Requisitos
- Python 3.9+
- pip o conda

#### Setup

```bash
# Clone the repository
git clone <repo-url>
cd tesla-tracker

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Initialize database with seed data
python -m app.database.init_db

# Run API
uvicorn app.api.main:app --reload --port 8000

# In another terminal, run Dashboard
streamlit run app/dashboard/app.py
```

**API** será accesible en: http://localhost:8000
**Dashboard** será accesible en: http://localhost:8501

### Opción 2: Docker Compose

```bash
# Build and start services
docker-compose up -d

# Initialize database (primera vez)
docker-compose exec tesla-api python -m app.database.init_db

# View logs
docker-compose logs -f
```

**API** en http://localhost:8000
**Dashboard** en http://localhost:8501

## 📚 API Documentation

Una vez que el API está corriendo, la documentación interactiva está disponible en:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Endpoints Principales

#### Health Check
```bash
GET /health
GET /
```

#### Reservations CRUD

```bash
# Get all reservations (con filtros opcionales)
GET /api/v1/reservations?status=BOOKED&model=Model%203&skip=0&limit=10

# Get specific reservation
GET /api/v1/reservations/{id}

# Create reservation
POST /api/v1/reservations
Content-Type: application/json

{
  "model": "Model 3",
  "color": "Solid Black",
  "wheels": "18\" Aero",
  "status": "RESERVED",
  "vin": "5YJ3E1EA1KF123456",
  "notes": "Optional notes"
}

# Update reservation
PUT /api/v1/reservations/{id}
Content-Type: application/json

{
  "status": "DELIVERED",
  "delivery_date": "2026-06-15T14:30:00"
}

# Delete reservation
DELETE /api/v1/reservations/{id}
```

#### Analytics

```bash
# Get statistics
GET /api/v1/stats
```

Response:
```json
{
  "total": 4,
  "by_status": {
    "RESERVED": 0,
    "BOOKED": 1,
    "PENDING_VIN": 1,
    "IN_TRANSIT": 1,
    "DELIVERED": 1
  },
  "by_model": {
    "Model 3": 1,
    "Model Y": 1,
    "Model S": 1,
    "Model X": 1
  },
  "timestamp": "2026-06-06T22:09:12.123Z"
}
```

## ⚙️ Configuration

Variables de entorno (ver `.env.example`):

```ini
# Database
DATABASE_URL=sqlite:///./data/tesla_tracker.db

# API
API_TITLE=Tesla Tracker API
API_VERSION=1.0.0
DEBUG=True
RELOAD=True

# Telegram Bot (para alertas)
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Groq AI (para predicciones)
GROQ_API_KEY=your_key_here
GROQ_MODEL=mixtral-8x7b-32768
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_api.py

# Run with verbose output
pytest -v
```

Coverage actual:
- `test_api.py`: 12 tests cobriendo CRUD, filtros, validación

## 📦 Project Structure

```
tesla-tracker/
├── app/
│   ├── api/              # FastAPI application
│   │   └── main.py       # Endpoints definition
│   ├── core/
│   │   └── config.py     # Configuration & settings
│   ├── database/
│   │   ├── database.py   # Database connection
│   │   ├── models.py     # SQLAlchemy ORM models
│   │   ├── schemas.py    # Pydantic schemas for validation
│   │   └── init_db.py    # Database initialization & seeding
│   ├── dashboard/
│   │   └── app.py        # Streamlit dashboard
│   ├── collectors/       # Data collectors (extensible)
│   │   ├── shipping.py   # Shipping data collector
│   │   └── reservation.py # Reservation data collector
│   ├── ai/               # AI/ML modules
│   │   ├── groq_client.py # Groq API client
│   │   └── predictor.py   # ETA prediction model
│   └── alerts/           # Notification modules
│       └── telegram.py    # Telegram alerts
├── tests/
│   └── test_api.py       # API tests
├── data/
│   └── tesla_tracker.db  # SQLite database (created at runtime)
├── Dockerfile            # Docker image definition
├── docker-compose.yml    # Multi-container setup
├── requirements.txt      # Python dependencies
├── .env.example          # Environment template
├── .gitignore            # Git ignore rules
├── Makefile              # Development commands
└── README.md             # This file
```

## 🔄 Data Flow

```
Tesla Order
    ↓
API (POST /reservations)
    ↓
Database (SQLite)
    ↓
┌───────────────────┐
├─ Dashboard (Streamlit)
├─ Alerts (Telegram)
├─ Predictor (Groq AI)
└─ Analytics Endpoints
```

## 🚦 Status Values

- `RESERVED` - Reservation created, not confirmed
- `BOOKED` - Order confirmed
- `PENDING_VIN` - Waiting for VIN assignment
- `IN_TRANSIT` - Vehicle en route to delivery
- `DELIVERED` - Successfully delivered

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 Roadmap

- [ ] WebSocket support para actualizaciones en tiempo real
- [ ] Email notifications
- [ ] PostgreSQL migration script
- [ ] Docker image optimization
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Mobile app (React Native)
- [ ] Advanced analytics dashboard
- [ ] Integration con Tesla API oficial
- [ ] Multi-vehicle support
- [ ] User authentication

## 📄 License

Este proyecto está bajo la licencia MIT. Ver `LICENSE` para más detalles.

## 👨‍💻 Author

Created with ❤️ for Tesla owners

---

**¿Necesitas ayuda?** Abre un issue o contacta al equipo de desarrollo.

**Last Updated**: Junio 2026
