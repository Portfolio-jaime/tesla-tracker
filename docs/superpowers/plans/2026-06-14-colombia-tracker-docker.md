# Colombia Purchase Tracker + Docker Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 6-step Colombia purchase timeline to the Tesla Tracker, redesign the Streamlit dashboard around it, and harden Docker with multi-stage builds, nginx, and dev/prod profiles.

**Architecture:** New `PurchaseStep` SQLAlchemy model + 2 FastAPI endpoints handle backend; Streamlit dashboard is rewritten to show a vertical timeline as primary view; a multi-stage Dockerfile replaces the current single-stage, and nginx routes prod traffic through port 80.

**Tech Stack:** FastAPI, SQLAlchemy (ORM-only writes), Pydantic v2, Streamlit, SQLite, Docker multi-stage, nginx:alpine

**Spec:** `docs/superpowers/specs/2026-06-13-colombia-tracker-docker.md`

---

## Chunk 1: Backend (Model + API)

### Task 1: PurchaseStep Model + Schemas

**Files:**
- Modify: `app/database/models.py`
- Modify: `app/database/schemas.py`
- Create: `tests/test_steps.py`

- [ ] **Step 1: Write failing test for model existence**

```python
# tests/test_steps.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.main import app
from app.database.database import get_db
from app.database.models import Base, PurchaseStep, STEP_KEYS

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_steps.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def make_reservation():
    r = client.post("/api/v1/reservations", json={"model": "Model Y", "color": "Gris Grafito"})
    assert r.status_code == 201
    return r.json()["id"]


class TestPurchaseStepModel:
    def test_step_keys_are_6(self):
        assert len(STEP_KEYS) == 6

    def test_step_keys_values(self):
        assert STEP_KEYS == [
            "RESERVA", "CONFIRMACION", "PRODUCCION",
            "ENVIO_MARITIMO", "ADUANA", "ENTREGA",
        ]

    def test_purchase_step_table_exists(self):
        db = TestingSessionLocal()
        try:
            count = db.query(PurchaseStep).count()
            assert count == 0
        finally:
            db.close()
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
cd /Users/jaime.henao/arheanja/tesla-tracker && source .venv/bin/activate && pytest tests/test_steps.py -v 2>&1 | head -30
```

Expected: `ImportError` — `PurchaseStep` and `STEP_KEYS` not defined yet.

- [ ] **Step 3: Add `PurchaseStep` model and `STEP_KEYS` to `app/database/models.py`**

Replace full file content:

```python
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

    def __repr__(self):  # keep existing repr
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
```

- [ ] **Step 4: Add Pydantic schemas to `app/database/schemas.py`**

Append at end of existing file:

```python
# --- Purchase Steps ---

class PurchaseStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reservation_id: int
    step_order: int
    step_key: str
    completed: bool
    completed_date: Optional[datetime] = None
    notes: Optional[str] = None
    updated_at: datetime


class PurchaseStepUpdate(BaseModel):
    completed: Optional[bool] = None
    completed_date: Optional[datetime] = None
    notes: Optional[str] = None
```

- [ ] **Step 5: Run test — expect PASS**

```bash
pytest tests/test_steps.py::TestPurchaseStepModel -v
```

Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/database/models.py app/database/schemas.py tests/test_steps.py
git commit -m "feat: add PurchaseStep model, STEP_KEYS, and Pydantic schemas

Co-Authored-By: jaimehenao8126 <jaimehenao8126@users.noreply.github.com>"
```

---

### Task 2: API Endpoints (GET + PATCH /steps)

**Files:**
- Modify: `app/api/main.py`
- Modify: `tests/test_steps.py` (add API test class)

- [ ] **Step 1: Write failing API tests — append to `tests/test_steps.py`**

```python
class TestStepsAPI:
    def test_get_steps_returns_6(self):
        res_id = make_reservation()
        r = client.get(f"/api/v1/reservations/{res_id}/steps")
        assert r.status_code == 200
        steps = r.json()
        assert len(steps) == 6

    def test_get_steps_order(self):
        res_id = make_reservation()
        steps = client.get(f"/api/v1/reservations/{res_id}/steps").json()
        keys = [s["step_key"] for s in steps]
        assert keys == ["RESERVA", "CONFIRMACION", "PRODUCCION", "ENVIO_MARITIMO", "ADUANA", "ENTREGA"]

    def test_get_steps_idempotent(self):
        res_id = make_reservation()
        client.get(f"/api/v1/reservations/{res_id}/steps")
        r = client.get(f"/api/v1/reservations/{res_id}/steps")
        assert r.status_code == 200
        assert len(r.json()) == 6

    def test_get_steps_404_unknown_reservation(self):
        r = client.get("/api/v1/reservations/9999/steps")
        assert r.status_code == 404

    def test_get_steps_all_incomplete_by_default(self):
        res_id = make_reservation()
        steps = client.get(f"/api/v1/reservations/{res_id}/steps").json()
        assert all(not s["completed"] for s in steps)

    def test_patch_step_marks_completed(self):
        res_id = make_reservation()
        r = client.patch(
            f"/api/v1/reservations/{res_id}/steps/RESERVA",
            json={"completed": True, "completed_date": "2026-05-09T00:00:00", "notes": "RN128096402"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["completed"] is True
        assert data["notes"] == "RN128096402"
        assert "2026-05-09" in data["completed_date"]

    def test_patch_step_invalid_key(self):
        res_id = make_reservation()
        r = client.patch(f"/api/v1/reservations/{res_id}/steps/INVALID", json={"completed": True})
        assert r.status_code == 400

    def test_patch_step_404_unknown_reservation(self):
        r = client.patch("/api/v1/reservations/9999/steps/RESERVA", json={"completed": True})
        assert r.status_code == 404

    def test_patch_step_autoseeds_if_no_get_called(self):
        res_id = make_reservation()
        # PATCH without prior GET — must auto-seed
        r = client.patch(
            f"/api/v1/reservations/{res_id}/steps/PRODUCCION",
            json={"completed": True},
        )
        assert r.status_code == 200
        assert r.json()["completed"] is True
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_steps.py::TestStepsAPI -v 2>&1 | head -30
```

Expected: `404 Not Found` — endpoints don't exist yet.

- [ ] **Step 3: Add helper `_ensure_steps` and two endpoints to `app/api/main.py`**

Add helper function (before the route definitions, after `VALID_STATUSES`):

```python
def _ensure_steps(reservation_id: int, db: Session) -> list:
    existing = (
        db.query(PurchaseStep)
        .filter(PurchaseStep.reservation_id == reservation_id)
        .all()
    )
    existing_keys = {s.step_key for s in existing}
    for i, key in enumerate(STEP_KEYS, start=1):
        if key not in existing_keys:
            db.add(PurchaseStep(
                reservation_id=reservation_id,
                step_order=i,
                step_key=key,
                completed=False,
            ))
    if len(existing_keys) < len(STEP_KEYS):
        db.commit()
    return (
        db.query(PurchaseStep)
        .filter(PurchaseStep.reservation_id == reservation_id)
        .order_by(PurchaseStep.step_order)
        .all()
    )
```

Add two new endpoints at end of file (before the stats endpoint or after it):

```python
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
    update_data = update.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    for field, value in update_data.items():
        setattr(step, field, value)
    db.add(step)
    db.commit()
    db.refresh(step)
    return step
```

- [ ] **Step 4: Fix the import in `app/api/main.py`** — the existing import line only imports `Reservation`:

Replace:
```python
from app.database.models import Base, Reservation
from app.database.schemas import ReservationCreate, ReservationUpdate, ReservationResponse, ReservationStatus
```

With:
```python
from app.database.models import Base, Reservation, PurchaseStep, STEP_KEYS
from app.database.schemas import (
    ReservationCreate, ReservationUpdate, ReservationResponse, ReservationStatus,
    PurchaseStepResponse, PurchaseStepUpdate,
)
```

- [ ] **Step 5: Run all step tests — expect PASS**

```bash
pytest tests/test_steps.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 6: Run full test suite — no regressions**

```bash
pytest tests/test_api.py -v
```

Expected: all existing tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/api/main.py tests/test_steps.py
git commit -m "feat: add GET and PATCH /steps endpoints with lazy auto-seed

Co-Authored-By: jaimehenao8126 <jaimehenao8126@users.noreply.github.com>"
```

---

## Chunk 2: Dashboard + Docker

### Task 3: Dashboard Redesign (Timeline UI)

**Precondition:** Task 1 (model + STEP_KEYS/STEP_LABELS) must be committed before starting this task. The dashboard imports `STEP_KEYS` and `STEP_LABELS` from `app.database.models` at module load time.

**Files:**
- Modify: `app/dashboard/app.py` (full rewrite)

No unit tests for Streamlit (not feasible without a browser harness). Verify manually after implementation.

- [ ] **Step 1: Replace `app/dashboard/app.py` with timeline-first design**

```python
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)

import requests
import streamlit as st
from datetime import datetime

from app.auth.tesla_auth import TeslaAuthManager
from app.database.models import STEP_KEYS, STEP_LABELS

st.set_page_config(
    page_title="Tesla Tracker",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auth gate ────────────────────────────────────────────────────────────────

_auth = TeslaAuthManager()
try:
    _has_session = _auth.has_valid_session()
except Exception:
    _auth.logout()
    _has_session = False

if not _has_session:
    from app.pages.login import render_login
    render_login(_auth)
    st.stop()

_cached_email = _auth.get_cached_email()
st.sidebar.success(f"Tesla: {_cached_email or 'conectado'}")

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

STEP_ICONS = {
    "RESERVA": "📋",
    "CONFIRMACION": "📄",
    "PRODUCCION": "🏭",
    "ENVIO_MARITIMO": "🚢",
    "ADUANA": "🛃",
    "ENTREGA": "🏠",
}

# ── Data fetchers ─────────────────────────────────────────────────────────────


@st.cache_data(ttl=30)
def fetch_reservations():
    try:
        r = requests.get(
            f"{API_BASE_URL}/api/v1/reservations",
            params={"skip": 0, "limit": 100},
            timeout=5,
        )
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=30)
def fetch_steps(reservation_id: int):
    try:
        r = requests.get(
            f"{API_BASE_URL}/api/v1/reservations/{reservation_id}/steps",
            timeout=5,
        )
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


# ── UI components ─────────────────────────────────────────────────────────────


def render_hero_card(res: dict):
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"## 🚗 Tesla {res['model']} — {res.get('color', '')}")
            rn = res.get("notes") or "—"
            order_date = (res.get("order_date") or "")[:10] or "—"
            st.caption(f"**{rn}** &nbsp;|&nbsp; Reservado: {order_date}")
        with col2:
            st.markdown(f"**Estado:** `{res['status']}`")


def render_edit_form(reservation_id: int, step: dict):
    key_prefix = f"step_{step['step_key']}"

    completed = st.checkbox(
        "Marcar como completado",
        value=step["completed"],
        key=f"{key_prefix}_completed",
    )

    date_val = None
    if step.get("completed_date"):
        try:
            date_val = datetime.fromisoformat(step["completed_date"][:19]).date()
        except Exception:
            date_val = None
    completed_date = st.date_input("Fecha", value=date_val, key=f"{key_prefix}_date")

    notes = st.text_input(
        "Notas (BL, pedimento, referencia...)",
        value=step.get("notes") or "",
        key=f"{key_prefix}_notes",
    )

    if st.button("Guardar", key=f"{key_prefix}_save"):
        payload = {
            "completed": completed,
            "completed_date": completed_date.isoformat() + "T00:00:00" if completed_date else None,
            "notes": notes or None,
        }
        try:
            r = requests.patch(
                f"{API_BASE_URL}/api/v1/reservations/{reservation_id}/steps/{step['step_key']}",
                json=payload,
                timeout=5,
            )
            if r.status_code == 200:
                st.success("Guardado ✓")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"Error {r.status_code}: {r.text}")
        except Exception as e:
            st.error(f"Error de conexión: {e}")


def render_timeline(reservation_id: int, steps: list):
    completed_count = sum(1 for s in steps if s["completed"])
    total = len(steps)

    st.progress(completed_count / total, text=f"{completed_count} / {total} pasos completados")
    st.markdown("---")

    all_done = completed_count == total
    if all_done:
        st.success("¡Entrega completada! 🎉")
        st.balloons()

    active_step = next((s for s in steps if not s["completed"]), None)

    for step in steps:
        icon = STEP_ICONS[step["step_key"]]
        label = STEP_LABELS[step["step_key"]]
        is_active = active_step and step["step_key"] == active_step["step_key"]

        if step["completed"]:
            date_str = (step.get("completed_date") or "")[:10] or "—"
            notes_str = f" — _{step['notes']}_" if step.get("notes") else ""
            st.markdown(f"✅ **{step['step_order']}. {label}** &nbsp;&nbsp; `{date_str}`{notes_str}")
            with st.expander(f"Editar: {label}"):
                render_edit_form(reservation_id, step)
        elif is_active:
            st.markdown(
                f"<div style='border-left: 4px solid #3E6AE1; padding-left: 12px;'>"
                f"🔵 <b>{step['step_order']}. {label}</b> &nbsp;&nbsp; <i>en progreso</i>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown("")
            with st.expander(f"✏️ Editar: {label}", expanded=True):
                render_edit_form(reservation_id, step)
        else:
            st.markdown(f"⬜ {step['step_order']}. {label}")


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Tesla Tracker")
    if st.button("Refrescar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    if st.button("Cerrar sesión Tesla", use_container_width=True):
        _auth.logout()
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── Main ──────────────────────────────────────────────────────────────────────

st.title("🚗 Tesla Tracker")

reservations, res_error = fetch_reservations()

if res_error:
    st.error(f"❌ No se puede conectar a la API: {res_error}")
    st.info("Asegúrate que la API está corriendo: `uvicorn app.api.main:app --reload`")
    st.stop()

if not reservations:
    st.info("No hay reservas. Agrega una desde la API en `/docs`.")
    st.stop()

# Reservation selector (sidebar if multiple, auto-select if one)
if len(reservations) == 1:
    selected = reservations[0]
else:
    options = {
        f"{r['model']} — {r.get('color', '')} [{r['status']}]": r
        for r in reservations
    }
    with st.sidebar:
        selected_label = st.selectbox("Reserva", list(options.keys()))
    selected = options[selected_label]

render_hero_card(selected)

st.markdown("### 📦 Estado de compra")

steps, steps_error = fetch_steps(selected["id"])

if steps_error:
    st.error(f"❌ Error cargando pasos: {steps_error}")
else:
    render_timeline(selected["id"], steps)

st.divider()
st.caption(f"Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
```

- [ ] **Step 2: Start the API + dashboard locally and verify**

Terminal 1:
```bash
cd /Users/jaime.henao/arheanja/tesla-tracker && source .venv/bin/activate
uvicorn app.api.main:app --reload --port 8000
```

Terminal 2:
```bash
source .venv/bin/activate
streamlit run app/dashboard/app.py
```

Open http://localhost:8501 — verify:
- Hero card shows Model Y, Gris Grafito, notes as RN
- 6 steps render in vertical timeline
- Step 1 (Reserva) is editable if not completed
- Clicking Guardar updates and reruns

- [ ] **Step 3: Commit**

```bash
git add app/dashboard/app.py
git commit -m "feat: redesign dashboard with Colombia 6-step purchase timeline

Co-Authored-By: jaimehenao8126 <jaimehenao8126@users.noreply.github.com>"
```

---

### Task 4: Docker (Multi-stage Dockerfile + compose + nginx)

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Create: `nginx.conf`

- [ ] **Step 1: Replace `Dockerfile` with multi-stage version**

```dockerfile
# Stage 1: install dependencies (shared base)
FROM python:3.12-slim-bookworm AS deps
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: production image (no dev tools, minimal footprint)
FROM deps AS production
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 3: dev image (hot-reload; extends deps not production — source is mounted via volume at runtime)
FROM deps AS dev
RUN pip install --no-cache-dir watchfiles
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000 8501
CMD ["uvicorn", "app.api.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Replace `docker-compose.yml`**

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      api:
        condition: service_healthy
      dashboard:
        condition: service_healthy
    networks:
      - tesla-network

  api:
    build:
      context: .
      target: production
    container_name: tesla-tracker-api
    env_file: .env
    volumes:
      - tesla-data:/app/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    networks:
      - tesla-network

  dashboard:
    build:
      context: .
      target: production
    container_name: tesla-tracker-dashboard
    env_file: .env
    environment:
      - API_BASE_URL=http://api:8000
    command: streamlit run app/dashboard/app.py --server.port=8501 --server.address=0.0.0.0
    volumes:
      - tesla-data:/app/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 20s
    depends_on:
      api:
        condition: service_healthy
    networks:
      - tesla-network

  api-dev:
    build:
      context: .
      target: dev
    profiles:
      - dev
    env_file: .env
    ports:
      - "8000:8000"
    volumes:
      - .:/app
      - tesla-data:/app/data
    networks:
      - tesla-network
    command: uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

  dashboard-dev:
    build:
      context: .
      target: dev
    profiles:
      - dev
    env_file: .env
    ports:
      - "8501:8501"
    environment:
      - API_BASE_URL=http://api-dev:8000
    volumes:
      - .:/app
      - tesla-data:/app/data
    networks:
      - tesla-network
    depends_on:
      - api-dev
    command: streamlit run app/dashboard/app.py --server.port=8501 --server.address=0.0.0.0

volumes:
  tesla-data:

networks:
  tesla-network:
    driver: bridge
```

- [ ] **Step 3: Create `nginx.conf` at repo root**

```nginx
server {
    listen 80;

    location /api/ {
        proxy_pass http://api:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /health {
        proxy_pass http://api:8000/health;
    }

    location /docs/ {
        proxy_pass http://api:8000/docs/;
        proxy_redirect http://api:8000/ /;
    }

    location = /docs {
        return 301 /docs/;
    }

    location /openapi.json {
        proxy_pass http://api:8000/openapi.json;
    }

    location / {
        proxy_pass http://dashboard:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

- [ ] **Step 4: Build and smoke-test prod stack**

```bash
cd /Users/jaime.henao/arheanja/tesla-tracker
docker compose build
docker compose up -d
```

Wait ~30 seconds for healthchecks to pass, then seed DB and verify:
```bash
# Seed the database (required first run — creates tables + purchase_steps support)
docker compose exec api python -m app.database.init_db

curl http://localhost/health
# Expected: {"status":"healthy","timestamp":"..."}

curl http://localhost/api/v1/reservations
# Expected: JSON array

open http://localhost
# Expected: Streamlit dashboard loads via nginx on port 80
```

- [ ] **Step 5: Smoke-test dev stack**

```bash
docker compose --profile dev up -d api-dev dashboard-dev
curl http://localhost:8000/health
open http://localhost:8501
```

Expected: both services hot-reload; code changes picked up without rebuild.

- [ ] **Step 6: Stop containers**

```bash
docker compose down
docker compose --profile dev down
```

- [ ] **Step 7: Commit**

```bash
git add Dockerfile docker-compose.yml nginx.conf
git commit -m "feat: multi-stage Docker build with nginx and dev/prod profiles

Co-Authored-By: jaimehenao8126 <jaimehenao8126@users.noreply.github.com>"
```
