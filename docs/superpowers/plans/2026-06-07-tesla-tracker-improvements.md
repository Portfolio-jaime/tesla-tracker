# Tesla Tracker Improvements — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar todos los tests corriendo, unificar el modelo de estados, mejorar el dashboard con timeline visual y KPIs, hacer los collectors configurables via env vars, y conectar las alertas de Telegram.

**Architecture:** Los fixes de tests y el modelo de estados son prerrequisitos para todo lo demás. El dashboard se mejora sobre Streamlit existente sin cambiar la arquitectura (sigue leyendo de la API). Los collectors leen de variables de entorno con fallback a datos de ejemplo. Las alertas Telegram se disparan desde ShippingCollector cuando cambia el estado.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, Streamlit, Pydantic v2, APScheduler, Telegram Bot API, pytest

---

## Chunk 1: Base sana — Fix de tests + Pydantic V2

### Task 1: Fix unicode en test_collectors.py

**Files:**
- Modify: `tests/test_collectors.py:123`

- [ ] **Step 1: Localizar el byte corrupto**

  Abrir `tests/test_collectors.py` línea 123. La cadena `"19-inch \xdcberturbine"` tiene un byte inválido en lugar de `Ü`.

- [ ] **Step 2: Corregir el carácter**

  Reemplazar:
  ```python
  "wheels": "19-inch \xdcberturbine",
  ```
  Por:
  ```python
  "wheels": "19-inch Überturbine",
  ```

- [ ] **Step 3: Verificar que el archivo parsea**

  ```bash
  python3 -c "import ast; ast.parse(open('tests/test_collectors.py').read()); print('OK')"
  ```
  Expected: `OK`

- [ ] **Step 4: Commit**

  ```bash
  git add tests/test_collectors.py
  git commit -m "fix: corregir byte unicode corrupto en test_collectors.py"
  ```

---

### Task 2: Instalar apscheduler

**Files:**
- No file changes (instalación de entorno)

- [ ] **Step 1: Confirmar que apscheduler está en requirements.txt**

  ```bash
  grep -i apscheduler requirements.txt
  ```
  Expected: `APScheduler==4.10.1` (ya está declarado).

- [ ] **Step 2: Instalar el paquete**

  ```bash
  pip install apscheduler
  ```

- [ ] **Step 3: Verificar que el módulo importa**

  ```bash
  python3 -c "from apscheduler.schedulers.background import BackgroundScheduler; print('OK')"
  ```
  Expected: `OK`

- [ ] **Step 4: Verificar que test_scheduler.py colecta**

  ```bash
  python3 -m pytest tests/test_scheduler.py --collect-only
  ```
  Expected: lista de tests sin errores de importación (mínimo 5 tests colectados).

---

### Task 3: Mover create_all a lifespan en app/api/main.py

> **Nota arquitectural:** El dashboard de Streamlit sigue leyendo los datos via la API REST (no directo de SQLite). Esta es la arquitectura existente y no cambia en este plan.

**Files:**
- Modify: `app/api/main.py`

- [ ] **Step 1: Reemplazar el import y la inicialización global**

  Archivo actual tiene en el top level:
  ```python
  Base.metadata.create_all(bind=engine)
  ```

  Reemplazar todo `app/api/main.py` con la versión corregida:

  ```python
  from contextlib import asynccontextmanager
  import os
  from fastapi import FastAPI, Depends, HTTPException, Query
  from sqlalchemy.orm import Session
  from datetime import datetime
  from typing import Optional, List

  from app.database.database import get_db, engine
  from app.database.models import Base, Reservation
  from app.database.schemas import ReservationCreate, ReservationUpdate, ReservationResponse
  from app.core.config import get_settings

  settings = get_settings()

  VALID_STATUSES = [
      "RESERVED", "CONFIRMED", "MANUFACTURING", "QUALITY_CHECK",
      "SHIPPING", "IN_TRANSIT", "DELIVERED", "CANCELLED",
  ]


  @asynccontextmanager
  async def lifespan(app: FastAPI):
      os.makedirs("data", exist_ok=True)
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
      return {"status": "healthy", "timestamp": datetime.utcnow()}


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
      update_data["updated_at"] = datetime.utcnow()
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


  @app.get("/api/v1/stats", tags=["Analytics"])
  def get_stats(db: Session = Depends(get_db)):
      total = db.query(Reservation).count()
      by_status = {s: db.query(Reservation).filter(Reservation.status == s).count() for s in VALID_STATUSES}
      by_model = {}
      for (model,) in db.query(Reservation.model).distinct():
          by_model[model] = db.query(Reservation).filter(Reservation.model == model).count()
      return {"total": total, "by_status": by_status, "by_model": by_model, "timestamp": datetime.utcnow()}
  ```

- [ ] **Step 2: Los tests existentes validan este cambio — correr test_api.py**

  Los tests de `TestHealth` y `TestReservationsCRUD` ya existentes son el criterio de verificación. Si pasan, el lifespan funciona correctamente.

  ```bash
  python3 -m pytest tests/test_api.py --collect-only
  ```
  Expected: 12 tests colectados sin `OperationalError`.

- [ ] **Step 3: Commit**

  ```bash
  git add app/api/main.py
  git commit -m "fix: mover create_all a lifespan, unificar VALID_STATUSES en API"
  ```

---

### Task 4: Corregir deprecation warnings de Pydantic V2

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/database/schemas.py`

- [ ] **Step 0: Confirmar que pydantic-settings está instalado**

  ```bash
  python3 -c "import pydantic_settings; print('OK')"
  ```
  Expected: `OK`. Si falla: `pip install pydantic-settings`.

- [ ] **Step 1: Actualizar app/core/config.py**

  ```python
  from pydantic_settings import BaseSettings
  from pydantic import ConfigDict
  from functools import lru_cache


  class Settings(BaseSettings):
      model_config = ConfigDict(env_file=".env", case_sensitive=True)

      DATABASE_URL: str = "sqlite:///./data/tesla_tracker.db"
      API_TITLE: str = "Tesla Tracker API"
      API_VERSION: str = "1.0.0"
      TELEGRAM_BOT_TOKEN: str = ""
      TELEGRAM_CHAT_ID: str = ""
      GROQ_API_KEY: str = ""
      GROQ_MODEL: str = "mixtral-8x7b-32768"
      DEBUG: bool = True
      RELOAD: bool = True
      WORKERS: int = 1


  @lru_cache()
  def get_settings() -> Settings:
      return Settings()
  ```

- [ ] **Step 2: Actualizar app/database/schemas.py**

  ```python
  from pydantic import BaseModel, Field, ConfigDict
  from datetime import datetime
  from typing import Literal, Optional

  ReservationStatus = Literal[
      "RESERVED", "CONFIRMED", "MANUFACTURING", "QUALITY_CHECK",
      "SHIPPING", "IN_TRANSIT", "DELIVERED", "CANCELLED",
  ]


  class ReservationBase(BaseModel):
      model: str = Field(..., min_length=1, max_length=50)
      color: Optional[str] = Field(None, max_length=50)
      wheels: Optional[str] = Field(None, max_length=50)
      status: ReservationStatus = "RESERVED"
      order_date: datetime = Field(default_factory=datetime.utcnow)
      eta_start: Optional[datetime] = None
      eta_end: Optional[datetime] = None
      delivery_date: Optional[datetime] = None
      vin: Optional[str] = Field(None, max_length=17)
      notes: Optional[str] = None


  class ReservationCreate(ReservationBase):
      pass


  class ReservationUpdate(BaseModel):
      model: Optional[str] = None
      color: Optional[str] = None
      wheels: Optional[str] = None
      status: Optional[ReservationStatus] = None
      eta_start: Optional[datetime] = None
      eta_end: Optional[datetime] = None
      delivery_date: Optional[datetime] = None
      vin: Optional[str] = None
      notes: Optional[str] = None


  class ReservationResponse(ReservationBase):
      model_config = ConfigDict(from_attributes=True)

      id: int
      created_at: datetime
      updated_at: datetime
  ```

- [ ] **Step 3: Correr tests y verificar que no hay warnings de Pydantic**

  ```bash
  python3 -m pytest tests/test_api.py -v -W error::DeprecationWarning 2>&1 | grep -E "(PASS|FAIL|ERROR|warning)"
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add app/core/config.py app/database/schemas.py
  git commit -m "fix: migrar a Pydantic V2 ConfigDict, agregar Literal para status"
  ```

---

### Task 5: Verificar baseline verde

- [ ] **Step 1: Correr todos los tests y verificar conteo**

  ```bash
  python3 -m pytest tests/ -v --tb=short 2>&1 | tail -10
  ```
  Expected mínimo aceptable después del Chunk 1:
  - `test_api.py`: **12 passed** (todos los tests de Health, CRUD y Stats)
  - `test_scheduler.py`: colectados y corriendo (puede haber fallos por mocks, no por import)
  - `test_collectors.py`: colectado sin SyntaxError (puede haber fallos de lógica — se abordan en Chunk 2)
  - Resumen final: `X passed, Y failed` — no debe haber `ERROR` en la línea de colección.

---

## Chunk 2: Modelo de estados unificado

### Task 6: Actualizar seeds en init_db.py

**Files:**
- Modify: `app/database/init_db.py`

- [ ] **Step 1: Reemplazar seeds con estados del nuevo vocabulario**

  ```python
  from datetime import datetime, timedelta
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
                  order_date=datetime.utcnow() - timedelta(days=60),
                  eta_start=datetime.utcnow() + timedelta(days=30),
                  eta_end=datetime.utcnow() + timedelta(days=45),
                  vin="5YJ3E1EA1KF123456",
                  notes="Configuración premium",
              ),
              Reservation(
                  model="Model Y",
                  color="Pearl White Multi-Coat",
                  wheels='19" Uberturbine',
                  status="MANUFACTURING",
                  order_date=datetime.utcnow() - timedelta(days=45),
                  eta_start=datetime.utcnow() + timedelta(days=15),
                  eta_end=datetime.utcnow() + timedelta(days=30),
                  notes="7 asientos",
              ),
              Reservation(
                  model="Model S",
                  color="Midnight Silver",
                  wheels='20" Überturbine',
                  status="IN_TRANSIT",
                  order_date=datetime.utcnow() - timedelta(days=90),
                  eta_start=datetime.utcnow() + timedelta(days=5),
                  eta_end=datetime.utcnow() + timedelta(days=10),
                  vin="5SAYGDEE7RL123456",
                  notes="En camino al centro de entrega",
              ),
              Reservation(
                  model="Model X",
                  color="Solid Black",
                  wheels='20" Überturbine',
                  status="DELIVERED",
                  order_date=datetime.utcnow() - timedelta(days=120),
                  delivery_date=datetime.utcnow() - timedelta(days=10),
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
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add app/database/init_db.py
  git commit -m "fix: actualizar seeds con estados del modelo unificado"
  ```

---

### Task 7: Actualizar tests de API para usar nuevos estados

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Ver cuántas ocurrencias hay que cambiar**

  ```bash
  grep -n '"BOOKED"\|"PENDING_VIN"' tests/test_api.py
  ```
  Expected: 5 líneas con `BOOKED`, 0 con `PENDING_VIN` (confirmar antes de reemplazar).

- [ ] **Step 2: Reemplazar todos los usos de una vez**

  ```bash
  sed -i '' 's/"BOOKED"/"CONFIRMED"/g' tests/test_api.py
  ```

  Verificar que no quedan ocurrencias:
  ```bash
  grep -n '"BOOKED"\|"PENDING_VIN"' tests/test_api.py
  ```
  Expected: sin output (0 matches).

  El método `test_get_reservations_filter_by_status` debe quedar:
  ```python
  def test_get_reservations_filter_by_status(self):
      client.post("/api/v1/reservations", json={"model": "Model 3", "status": "CONFIRMED"})
      client.post("/api/v1/reservations", json={"model": "Model Y", "status": "DELIVERED"})

      response = client.get("/api/v1/reservations?status=CONFIRMED")
      assert response.status_code == 200
      assert len(response.json()) == 1
      assert response.json()[0]["status"] == "CONFIRMED"
  ```

  Y `test_update_reservation`:
  ```python
  def test_update_reservation(self):
      create_response = client.post("/api/v1/reservations", json={"model": "Model 3", "status": "CONFIRMED"})
      reservation_id = create_response.json()["id"]

      response = client.put(f"/api/v1/reservations/{reservation_id}", json={"status": "DELIVERED"})
      assert response.status_code == 200
      assert response.json()["status"] == "DELIVERED"
  ```

- [ ] **Step 2: Correr los tests de API**

  ```bash
  python3 -m pytest tests/test_api.py -v
  ```
  Expected: todos en verde.

- [ ] **Step 3: Commit**

  ```bash
  git add tests/test_api.py
  git commit -m "fix: actualizar tests para usar modelo de estados unificado"
  ```

---

### Task 8: Actualizar mocks en ReservationCollector

> **Nota:** Task 11 (Chunk 4) reemplaza `fetch_reservations()` completo con lógica configurable via env vars. Si ejecutas Chunk 4 inmediatamente después, **puedes saltar este task** — Task 11 incluye los mocks correctos con los estados unificados.

**Files:**
- Modify: `app/collectors/reservation.py`

- [ ] **Step 1: Localizar el método y reemplazar solo la lista `reservations_data`**

  El método tiene esta estructura — reemplazar únicamente el bloque de la lista:
  ```python
  def fetch_reservations(self) -> List[Dict[str, Any]]:
      try:
          self.logger.info("Fetching reservations from external source...")
          reservations_data = [
              # ← REEMPLAZAR SOLO ESTE BLOQUE
          ]
          self.logger.info(f"Successfully fetched {len(reservations_data)} reservations")
          return reservations_data
      except Exception as e:
          ...
  ```

  El nuevo bloque:
  ```python
  reservations_data = [
      {
          "model": "Model 3",
          "color": "Midnight Black",
          "wheels": "18-inch Aero",
          "status": "CONFIRMED",
          "order_date": datetime(2024, 1, 15),
          "eta_start": datetime(2024, 3, 1),
          "eta_end": datetime(2024, 4, 30),
          "vin": "5YJ3E1EA0JF123456",
          "notes": "Premium interior, Full Self-Driving",
      },
      {
          "model": "Model Y",
          "color": "Pearl White",
          "wheels": "20-inch Aero",
          "status": "MANUFACTURING",
          "order_date": datetime(2024, 2, 1),
          "eta_start": datetime(2024, 4, 15),
          "eta_end": datetime(2024, 5, 31),
          "vin": "5YJ3E1EA0JF123457",
          "notes": "7-seater configuration",
      },
      {
          "model": "Model S",
          "color": "Solid Black",
          "wheels": "19-inch Überturbine",
          "status": "IN_TRANSIT",
          "order_date": datetime(2024, 1, 1),
          "eta_start": datetime(2024, 3, 15),
          "eta_end": datetime(2024, 4, 15),
          "delivery_date": datetime(2024, 4, 10),
          "vin": "5YJ3E1EA0JF123458",
          "notes": "Long Range",
      },
  ]
  ```

- [ ] **Step 2: Correr todos los tests**

  ```bash
  python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add app/collectors/reservation.py
  git commit -m "fix: actualizar estados en datos simulados del ReservationCollector"
  ```

---

## Chunk 3: Dashboard mejorado

### Task 9: Mejorar app/dashboard/app.py

**Files:**
- Modify: `app/dashboard/app.py`

- [ ] **Step 1: Reescribir el dashboard completo**

  ```python
  import streamlit as st
  import requests
  import pandas as pd
  from datetime import datetime
  import plotly.express as px

  st.set_page_config(
      page_title="Tesla Tracker Dashboard",
      page_icon="🚗",
      layout="wide",
      initial_sidebar_state="expanded",
  )

  API_BASE_URL = "http://localhost:8000"

  STATUS_PROGRESSION = [
      "RESERVED", "CONFIRMED", "MANUFACTURING",
      "QUALITY_CHECK", "SHIPPING", "IN_TRANSIT", "DELIVERED",
  ]

  STATUS_LABELS = {
      "RESERVED": "📋 Reservado",
      "CONFIRMED": "✅ Confirmado",
      "MANUFACTURING": "🏭 Fabricando",
      "QUALITY_CHECK": "🔍 Control QC",
      "SHIPPING": "📦 Enviando",
      "IN_TRANSIT": "🚛 En Tránsito",
      "DELIVERED": "🏠 Entregado",
      "CANCELLED": "❌ Cancelado",
  }

  ALL_STATUSES = STATUS_PROGRESSION + ["CANCELLED"]


  @st.cache_data(ttl=30)
  def fetch_reservations(status=None, model=None):
      try:
          params = {"skip": 0, "limit": 100}
          if status and status != "All":
              params["status"] = status
          if model:
              params["model"] = model
          r = requests.get(f"{API_BASE_URL}/api/v1/reservations", params=params, timeout=5)
          r.raise_for_status()
          return r.json(), None
      except Exception as e:
          return None, str(e)


  @st.cache_data(ttl=30)
  def fetch_stats():
      try:
          r = requests.get(f"{API_BASE_URL}/api/v1/stats", timeout=5)
          r.raise_for_status()
          return r.json(), None
      except Exception as e:
          return None, str(e)


  def render_status_timeline(current_status: str):
      if current_status == "CANCELLED":
          st.error("❌ Esta reserva fue cancelada")
          return

      try:
          idx = STATUS_PROGRESSION.index(current_status)
      except ValueError:
          idx = 0

      progress = idx / (len(STATUS_PROGRESSION) - 1)
      st.progress(progress)

      cols = st.columns(len(STATUS_PROGRESSION))
      for i, (col, status) in enumerate(zip(cols, STATUS_PROGRESSION)):
          label = STATUS_LABELS[status]
          with col:
              if i < idx:
                  st.markdown(f"<center>✅<br><small>{label}</small></center>", unsafe_allow_html=True)
              elif i == idx:
                  st.markdown(f"<center>🔵<br><small><b>{label}</b></small></center>", unsafe_allow_html=True)
              else:
                  st.markdown(f"<center>⚪<br><small>{label}</small></center>", unsafe_allow_html=True)


  def eta_days_remaining(eta_end_str) -> str:
      if not eta_end_str:
          return "Sin ETA"
      try:
          eta_end = datetime.fromisoformat(str(eta_end_str).replace("Z", ""))
          delta = (eta_end - datetime.utcnow()).days
          if delta < 0:
              return "Vencida"
          return f"{delta} días"
      except Exception:
          return "—"


  # ============================================================================
  # Sidebar
  # ============================================================================

  with st.sidebar:
      st.header("Filtros")
      status_filter = st.selectbox("Estado", ["All"] + ALL_STATUSES)
      model_filter = st.text_input("Modelo", placeholder="e.g., Model 3")
      if st.button("🔄 Refrescar", use_container_width=True):
          st.cache_data.clear()
          st.rerun()

  # ============================================================================
  # Header
  # ============================================================================

  st.title("🚗 Tesla Tracker")

  # ============================================================================
  # KPIs
  # ============================================================================

  stats_data, stats_error = fetch_stats()

  if stats_data:
      by_status = stats_data.get("by_status", {})
      in_transit = by_status.get("IN_TRANSIT", 0) + by_status.get("SHIPPING", 0)
      delivered = by_status.get("DELIVERED", 0)

      # Próxima entrega: menor eta_end de reservas activas
      all_res, _ = fetch_reservations()
      next_eta = "—"
      if all_res:
          active = [r for r in all_res if r.get("eta_end") and r.get("status") not in ("DELIVERED", "CANCELLED")]
          if active:
              soonest = min(active, key=lambda r: r["eta_end"])
              next_eta = eta_days_remaining(soonest["eta_end"]) + f" ({soonest['model']})"

      col1, col2, col3, col4 = st.columns(4)
      col1.metric("Total", stats_data["total"])
      col2.metric("En Tránsito", in_transit)
      col3.metric("Entregados", delivered)
      col4.metric("Próxima entrega", next_eta)

  st.divider()

  # ============================================================================
  # Datos principales
  # ============================================================================

  reservations_data, res_error = fetch_reservations(
      status=None if status_filter == "All" else status_filter,
      model=model_filter or None,
  )

  if res_error:
      st.error(f"❌ Error: {res_error}")
      st.info("Asegúrate que la API está corriendo: `uvicorn app.api.main:app --reload`")
      st.stop()

  # ============================================================================
  # Detalle de reserva seleccionada
  # ============================================================================

  if reservations_data:
      options = {
          f"{r['model']} — VIN: {r.get('vin', 'Sin VIN')[:10] or 'N/A'} [{r['status']}]": r
          for r in reservations_data
      }
      selected_label = st.selectbox("Selecciona un vehículo para ver detalle", list(options.keys()))
      selected = options[selected_label]

      with st.container(border=True):
          st.subheader(f"🚗 {selected['model']} — {selected.get('color', '')}")
          render_status_timeline(selected["status"])

          c1, c2, c3 = st.columns(3)
          c1.metric("Estado actual", STATUS_LABELS.get(selected["status"], selected["status"]))
          c2.metric("ETA restante", eta_days_remaining(selected.get("eta_end")))
          c3.metric("VIN", selected.get("vin") or "Sin asignar")

          if selected.get("notes"):
              st.caption(f"📝 {selected['notes']}")

  st.divider()

  # ============================================================================
  # Distribución + tabla
  # ============================================================================

  col_chart, col_table = st.columns([1, 2])

  with col_chart:
      st.subheader("📊 Por estado")
      if stats_data:
          status_df = pd.DataFrame(
              [(k, v) for k, v in stats_data["by_status"].items() if v > 0],
              columns=["Estado", "Count"],
          )
          if not status_df.empty:
              fig = px.pie(status_df, values="Count", names="Estado", hole=0.4)
              fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
              st.plotly_chart(fig, use_container_width=True)

  with col_table:
      st.subheader("📋 Lista de reservas")
      if reservations_data:
          df = pd.DataFrame(reservations_data)
          display_cols = ["id", "model", "color", "status", "vin", "eta_start", "eta_end"]
          df_display = df[[c for c in display_cols if c in df.columns]]
          st.dataframe(
              df_display,
              use_container_width=True,
              hide_index=True,
              column_config={
                  "id": st.column_config.NumberColumn("ID", width="small"),
                  "model": st.column_config.TextColumn("Modelo"),
                  "color": st.column_config.TextColumn("Color"),
                  "status": st.column_config.TextColumn("Estado"),
                  "vin": st.column_config.TextColumn("VIN"),
                  "eta_start": st.column_config.DatetimeColumn("ETA Inicio"),
                  "eta_end": st.column_config.DatetimeColumn("ETA Fin"),
              },
          )
          st.caption(f"Mostrando {len(reservations_data)} reservas")
      else:
          st.info("No hay reservas")

  # ============================================================================
  # Footer
  # ============================================================================

  st.divider()
  st.caption(f"Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  ```

- [ ] **Step 2: Verificar que el dashboard arranca sin errores de sintaxis**

  ```bash
  python3 -c "import ast; ast.parse(open('app/dashboard/app.py').read()); print('OK')"
  ```
  Expected: `OK`

- [ ] **Step 3: Commit**

  ```bash
  git add app/dashboard/app.py
  git commit -m "feat: dashboard con timeline visual, KPIs, detalle por reserva y pie chart"
  ```

---

## Chunk 4: Collectors configurables + Alertas Telegram

### Task 10: Agregar env vars de Tesla a config y .env.example

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Agregar campos opcionales en Settings**

  En `app/core/config.py`, dentro de `class Settings`, agregar después de `WORKERS`:
  ```python
  # Tesla vehicle config (optional — if set, overrides mock data in collectors)
  TESLA_VIN: str = ""
  TESLA_MODEL: str = ""
  TESLA_COLOR: str = ""
  TESLA_STATUS: str = "RESERVED"
  TESLA_ETA_START: str = ""  # ISO format: 2026-07-01
  TESLA_ETA_END: str = ""    # ISO format: 2026-07-15
  ```

- [ ] **Step 2: Actualizar .env.example**

  Agregar al final de `.env.example`:
  ```ini
  # Tesla vehicle (optional — completa para usar datos reales en lugar de mocks)
  TESLA_VIN=
  TESLA_MODEL=
  TESLA_COLOR=
  TESLA_STATUS=RESERVED
  TESLA_ETA_START=
  TESLA_ETA_END=
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add app/core/config.py .env.example
  git commit -m "feat: agregar env vars de Tesla para configurar collectors"
  ```

---

### Task 11: Hacer ReservationCollector configurable via env vars

**Files:**
- Modify: `app/collectors/reservation.py`

- [ ] **Step 1: Actualizar fetch_reservations() para leer de settings**

  Reemplazar el método `fetch_reservations()` completo:
  ```python
  def fetch_reservations(self) -> List[Dict[str, Any]]:
      try:
          self.logger.info("Fetching reservations from external source...")
          settings = get_settings()

          if settings.TESLA_VIN and settings.TESLA_MODEL:
              self.logger.info("Usando datos de variables de entorno TESLA_*")
              data: Dict[str, Any] = {
                  "model": settings.TESLA_MODEL,
                  "status": settings.TESLA_STATUS or "RESERVED",
                  "vin": settings.TESLA_VIN,
              }
              if settings.TESLA_COLOR:
                  data["color"] = settings.TESLA_COLOR
              if settings.TESLA_ETA_START:
                  data["eta_start"] = datetime.fromisoformat(settings.TESLA_ETA_START)
              if settings.TESLA_ETA_END:
                  data["eta_end"] = datetime.fromisoformat(settings.TESLA_ETA_END)
              return [data]

          self.logger.info("TESLA_VIN no configurado — usando datos de ejemplo")
          return [
              {
                  "model": "Model 3",
                  "color": "Midnight Black",
                  "wheels": "18-inch Aero",
                  "status": "CONFIRMED",
                  "order_date": datetime(2024, 1, 15),
                  "eta_start": datetime(2024, 3, 1),
                  "eta_end": datetime(2024, 4, 30),
                  "vin": "5YJ3E1EA0JF123456",
                  "notes": "Premium interior, Full Self-Driving",
              },
              {
                  "model": "Model Y",
                  "color": "Pearl White",
                  "wheels": "20-inch Aero",
                  "status": "MANUFACTURING",
                  "order_date": datetime(2024, 2, 1),
                  "eta_start": datetime(2024, 4, 15),
                  "eta_end": datetime(2024, 5, 31),
                  "vin": "5YJ3E1EA0JF123457",
                  "notes": "7-seater configuration",
              },
              {
                  "model": "Model S",
                  "color": "Solid Black",
                  "wheels": "19-inch Überturbine",
                  "status": "IN_TRANSIT",
                  "order_date": datetime(2024, 1, 1),
                  "eta_start": datetime(2024, 3, 15),
                  "eta_end": datetime(2024, 4, 15),
                  "delivery_date": datetime(2024, 4, 10),
                  "vin": "5YJ3E1EA0JF123458",
                  "notes": "Long Range",
              },
          ]
      except Exception as e:
          self.logger.error(f"Error fetching reservations: {str(e)}", exc_info=True)
          raise
  ```

  También agregar el import al inicio del archivo:
  ```python
  from app.core.config import get_settings
  ```

- [ ] **Step 2: Verificar sintaxis e import**

  ```bash
  python3 -c "from app.collectors.reservation import ReservationCollector; print('OK')"
  ```
  Expected: `OK`

- [ ] **Step 3: Commit**

  ```bash
  git add app/collectors/reservation.py
  git commit -m "feat: ReservationCollector lee de env vars TESLA_* con fallback a mocks"
  ```

---

### Task 12: Implementar TelegramAlert

**Files:**
- Modify: `app/alerts/telegram.py`

- [ ] **Step 1: Implementar la clase TelegramAlert**

  ```python
  import logging
  import requests

  logger = logging.getLogger(__name__)


  class TelegramAlert:
      BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

      def __init__(self, token: str, chat_id: str):
          self.token = token
          self.chat_id = chat_id
          self._configured = bool(token and chat_id)

      def send(self, model: str, vin: str, old_status: str, new_status: str) -> bool:
          message = (
              f"🚗 *{model}*\n"
              f"VIN: `{vin or 'Sin VIN'}`\n"
              f"Estado: {old_status} → *{new_status}*"
          )
          if new_status == "DELIVERED":
              message += "\n✅ ¡Entrega confirmada!"
          elif new_status == "IN_TRANSIT":
              message += "\n🚛 En camino a tu centro de entrega"

          if not self._configured:
              logger.info(f"[TelegramAlert] Sin configurar — alerta local: {message.replace('*', '').replace('`', '')}")
              return False

          try:
              url = self.BASE_URL.format(token=self.token)
              response = requests.post(
                  url,
                  json={"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"},
                  timeout=5,
              )
              response.raise_for_status()
              logger.info(f"Alerta Telegram enviada: {model} ({vin}) → {new_status}")
              return True
          except Exception as e:
              logger.error(f"Error enviando alerta Telegram: {e}")
              return False
  ```

- [ ] **Step 2: Verificar sintaxis**

  ```bash
  python3 -c "from app.alerts.telegram import TelegramAlert; print('OK')"
  ```
  Expected: `OK`

- [ ] **Step 3: Commit**

  ```bash
  git add app/alerts/telegram.py
  git commit -m "feat: implementar TelegramAlert con envío real via Telegram Bot API"
  ```

---

### Task 13: Conectar alertas a ShippingCollector

**Files:**
- Modify: `app/collectors/shipping.py`

- [ ] **Step 1: Agregar import y inicialización de TelegramAlert**

  Al inicio de `shipping.py`, agregar el import:
  ```python
  from app.alerts.telegram import TelegramAlert
  from app.core.config import get_settings
  ```

  En `__init__` de `ShippingCollector`, agregar después de `self.is_managed_session`:
  ```python
  _settings = get_settings()
  self._alert = TelegramAlert(
      token=_settings.TELEGRAM_BOT_TOKEN,
      chat_id=_settings.TELEGRAM_CHAT_ID,
  )
  ```

- [ ] **Step 2: Disparar alerta cuando cambia el estado**

  En `update_reservations()`, localizar este bloque (líneas ~189-193 del archivo original):
  ```python
  reservation.status = new_status
  reservation.eta_start = update.get(
      "eta_start", reservation.eta_start
  )
  ```

  Agregar el dispatch de alerta **inmediatamente después de `reservation.status = new_status`**:
  ```python
  reservation.status = new_status
  if new_status != old_status:
      self._alert.send(
          model=reservation.model,
          vin=reservation.vin or "",
          old_status=old_status,
          new_status=new_status,
      )
  reservation.eta_start = update.get(
      "eta_start", reservation.eta_start
  )
  ```

- [ ] **Step 3: Verificar que los tests de shipping siguen pasando**

  ```bash
  python3 -m pytest tests/test_collectors.py tests/test_shipping_collector.py -v --tb=short 2>&1 | tail -20
  ```

- [ ] **Step 4: Correr la suite completa**

  ```bash
  python3 -m pytest tests/ -v --tb=short 2>&1 | tail -30
  ```
  Expected: todos en verde.

- [ ] **Step 5: Commit final**

  ```bash
  git add app/collectors/shipping.py
  git commit -m "feat: conectar TelegramAlert a ShippingCollector en cambios de estado"
  ```

---

## Verificación final

- [ ] **Correr todos los tests**

  ```bash
  python3 -m pytest tests/ -v 2>&1 | tail -30
  ```

- [ ] **Probar la app manualmente**

  Terminal 1:
  ```bash
  python3 -m app.database.init_db
  uvicorn app.api.main:app --reload --port 8000
  ```

  Terminal 2:
  ```bash
  streamlit run app/dashboard/app.py
  ```

  Abrir http://localhost:8501 y verificar:
  - [ ] KPIs se muestran en la parte superior
  - [ ] Timeline visual aparece al seleccionar una reserva
  - [ ] Pie chart de distribución por estado
  - [ ] El filtro de estados en sidebar usa los estados nuevos
