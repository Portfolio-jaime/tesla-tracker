# Design Spec: Colombia Purchase Tracker + Docker Improvements

## Goal

Replace the generic status dropdown with a 6-step Colombia-specific purchase timeline, redesign the dashboard around that timeline, and harden the Docker setup with multi-stage builds, nginx, and dev/prod profiles.

---

## 1. Data Model

### New table: `purchase_steps`

| Column           | Type     | Constraints                        |
|------------------|----------|------------------------------------|
| id               | INTEGER  | PK                                 |
| reservation_id   | INTEGER  | FK → reservations.id, NOT NULL     |
| step_order       | INTEGER  | 1–6, NOT NULL                      |
| step_key         | TEXT     | NOT NULL (see keys below)          |
| completed        | BOOLEAN  | default false                      |
| completed_date   | DATETIME | nullable                           |
| notes            | TEXT     | nullable                           |
| updated_at       | DATETIME | default now, auto-update on write  |

**Step keys (fixed, in order):**

| step_order | step_key        | Label                |
|------------|-----------------|----------------------|
| 1          | RESERVA         | Reserva              |
| 2          | CONFIRMACION    | Confirmación de orden|
| 3          | PRODUCCION      | Producción           |
| 4          | ENVIO_MARITIMO  | Envío marítimo       |
| 5          | ADUANA          | Aduana Colombia      |
| 6          | ENTREGA         | Entrega              |

**Lifecycle:** When a `Reservation` is created (or on first GET of steps for an existing reservation), all 6 `PurchaseStep` rows are auto-created with `completed=false`. Step names/order are never editable — only `completed`, `completed_date`, and `notes`.

### Existing `reservations` table

No schema changes. The `status` field is kept for compatibility but is no longer the primary UX driver — the timeline replaces it visually.

---

## 2. API

Two new endpoints on the existing FastAPI app:

### `GET /api/v1/reservations/{id}/steps`

Returns the 6 steps for a reservation. Auto-creates them if missing (idempotent).

Response: list of step objects sorted by `step_order`.

```json
[
  {
    "id": 1,
    "reservation_id": 1,
    "step_order": 1,
    "step_key": "RESERVA",
    "completed": true,
    "completed_date": "2026-05-09T00:00:00Z",
    "notes": "RN128096402",
    "updated_at": "2026-06-01T10:00:00Z"
  },
  ...
]
```

### `PATCH /api/v1/reservations/{id}/steps/{step_key}`

Updates `completed`, `completed_date`, and/or `notes` for one step.

Request body (all fields optional):
```json
{
  "completed": true,
  "completed_date": "2026-05-09T00:00:00",
  "notes": "BL número: ABCD1234"
}
```

Returns the updated step object.

**Validation:** `step_key` must be one of the 6 valid keys; 404 if reservation not found; 400 if invalid key.

---

## 3. Dashboard UI

### Layout

```
┌─────────────────────────────────────────────────┐
│  🚗 Tesla Model Y — Gris Grafito                │
│  RN128096402  |  Reservado: 9 May 2026  | BOOKED │
│  ████████░░░░░░░░  2 / 6 pasos (33%)            │
└─────────────────────────────────────────────────┘

  ✅  1. Reserva           09 May 2026   RN128096402
  ✅  2. Confirmación      15 May 2026   orden confirmada
  🔵  3. Producción        ── activo ──
  ⬜  4. Envío Marítimo    pendiente
  ⬜  5. Aduana Colombia   pendiente
  ⬜  6. Entrega           pendiente

  [▼ Editar: Producción]
    Marcar completado: [ ] 
    Fecha: [__________]
    Notas: [__________]
    [Guardar]
```

### Behavior

- **Active step** = first step where `completed=false` → highlighted in Tesla blue (#3E6AE1)
- **Completed steps** → green checkmark + date + notes (if any)
- **Pending steps** → grey, no date
- **Edit form** → inline expander under the active step; any step can be clicked to edit
- **Progress bar** → `completed_count / 6` displayed as `st.progress()` + label
- **Hero card** → shows model, color, RN (from `notes` of step 1 or reservation notes), order date, current `status`

### Pages structure

The dashboard replaces the existing status-based view. The timeline is the primary view for a single reservation (the user currently has one). A sidebar selector remains for future multi-reservation support.

---

## 4. Docker

### Multi-stage Dockerfile

```
Stage 1 — deps:    python:3.12-slim, pip install requirements.txt
Stage 2 — prod:    copy app code only, no dev tools
Stage 3 — dev:     extends prod, adds watchfiles for hot-reload
```

Single Dockerfile, target selected per service in compose.

### docker-compose.yml

```yaml
services:
  nginx:
    image: nginx:alpine
    ports: ["80:80"]
    volumes: [./nginx.conf:/etc/nginx/conf.d/default.conf:ro]
    depends_on: [api, dashboard]

  api:
    build: { context: ., target: production }
    env_file: .env
    volumes: [tesla-data:/app/data]
    healthcheck: (existing)
    networks: [tesla-network]

  dashboard:
    build: { context: ., target: production }
    env_file: .env
    volumes: [tesla-data:/app/data]
    command: streamlit run app/dashboard/app.py --server.port=8501 --server.address=0.0.0.0
    depends_on:
      api: { condition: service_healthy }
    networks: [tesla-network]

  api-dev:
    build: { context: ., target: dev }
    profiles: [dev]
    env_file: .env
    ports: ["8000:8000"]
    volumes: [.:/app, tesla-data:/app/data]
    command: uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

  dashboard-dev:
    build: { context: ., target: dev }
    profiles: [dev]
    env_file: .env
    ports: ["8501:8501"]
    volumes: [.:/app, tesla-data:/app/data]
    command: streamlit run app/dashboard/app.py --server.port=8501 --server.address=0.0.0.0

volumes:
  tesla-data:
networks:
  tesla-network:
    driver: bridge
```

### nginx.conf

```nginx
server {
    listen 80;
    location /api { proxy_pass http://api:8000; }
    location /docs { proxy_pass http://api:8000/docs; }
    location / { proxy_pass http://dashboard:8501; }
}
```

### Usage

```bash
docker compose up -d              # prod (nginx on :80)
docker compose --profile dev up   # dev with hot-reload
```

---

## 5. Testing

- Unit: `PurchaseStep` model creation, auto-seed of 6 steps
- API: GET steps returns 6 rows; PATCH updates correctly; invalid step_key returns 400
- Integration: steps auto-created on first GET even if reservation existed before migration
- Docker: `docker compose up` → nginx proxies `/api/health` correctly; dashboard loads at `/`

---

## Out of Scope

- Push notifications / Telegram alerts per step (future)
- Multi-user support
- Step history / audit log
- File attachment per step (photos of documents)
