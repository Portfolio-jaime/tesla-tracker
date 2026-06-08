# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Initialize DB with seed data (required first run)
python -m app.database.init_db

# Run API (port 8000)
uvicorn app.api.main:app --reload --port 8000

# Run Dashboard (port 8501, separate terminal)
streamlit run app/dashboard/app.py

# Tests
pytest
pytest tests/test_api.py          # single file
pytest -v --cov=app               # with coverage

# Docker
docker-compose up -d
docker-compose exec tesla-api python -m app.database.init_db
```

Interactive API docs at `http://localhost:8000/docs` once the API is running.

## Architecture

FastAPI backend + Streamlit frontend + SQLite, with optional background collectors and AI-powered ETA prediction.

**Request flow:**
```
HTTP Request → app/api/main.py → SQLAlchemy (app/database/) → SQLite
                                      ↓
                          app/alerts/telegram.py
                          app/ai/predictor.py (Groq API)
                          app/dashboard/app.py (reads DB directly)
```

**Key modules:**

- `app/api/main.py` — All FastAPI endpoints. Tables auto-created on startup via `Base.metadata.create_all`.
- `app/database/models.py` — Single `Reservation` model (SQLAlchemy ORM). Indexed on `status`, `order_date`, `vin`.
- `app/database/schemas.py` — Pydantic schemas: `ReservationCreate`, `ReservationUpdate`, `ReservationResponse`.
- `app/database/database.py` — SQLAlchemy engine + `get_db` dependency (session-per-request pattern).
- `app/core/config.py` — `Settings` via `pydantic_settings`, loaded from `.env`. Accessed via `get_settings()` (cached).
- `app/collectors/scheduler.py` — `CollectorScheduler` wraps APScheduler. Runs `ReservationCollector` (every 6h) and `ShippingCollector` (every 3h) as background jobs. Uses a global singleton via `get_scheduler()`.
- `app/ai/groq_client.py` + `app/ai/predictor.py` — Groq API integration (Mixtral) for delivery date prediction.
- `app/alerts/telegram.py` — Telegram Bot API for push notifications.
- `app/dashboard/app.py` — Streamlit app, reads from the same SQLite DB.

**Reservation status lifecycle:** `RESERVED` → `BOOKED` → `PENDING_VIN` → `IN_TRANSIT` → `DELIVERED`

## Environment Variables

Required in `.env` for full functionality (see `.env.example`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite path (default: `sqlite:///./data/tesla_tracker.db`) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Alerts (optional) |
| `GROQ_API_KEY` | AI predictions (optional) |
| `GROQ_MODEL` | Defaults to `mixtral-8x7b-32768` |

The `data/` directory is created at runtime and holds the SQLite file — it's git-ignored.
