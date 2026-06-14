# Design Spec: Colombia Purchase Tracker + Docker Improvements

## Goal

Replace the generic status dropdown with a 6-step Colombia-specific purchase timeline, redesign the dashboard around that timeline, and harden the Docker setup with multi-stage builds, nginx, and dev/prod profiles.

---

## 1. Data Model

### New table: `purchase_steps`

| Column           | Type     | Constraints                                      |
|------------------|----------|--------------------------------------------------|
| id               | INTEGER  | PK                                               |
| reservation_id   | INTEGER  | FK → reservations.id, NOT NULL                   |
| step_order       | INTEGER  | 1–6, NOT NULL                                    |
| step_key         | TEXT     | NOT NULL (see keys below)                        |
| completed        | BOOLEAN  | default false                                    |
| completed_date   | DATETIME | nullable                                         |
| notes            | TEXT     | nullable                                         |
| updated_at       | DATETIME | `default=datetime.utcnow, onupdate=datetime.utcnow` (function reference, not call — matches existing Reservation model) |

**Unique constraints:** `UNIQUE(reservation_id, step_order)` and `UNIQUE(reservation_id, step_key)`.

**ORM-only writes required.** All inserts and updates to `purchase_steps` must go through SQLAlchemy ORM (not raw SQL) so that `updated_at` fires via `onupdate=`.

**Step keys (fixed, in order):**

| step_order | step_key        | Label                |
|------------|-----------------|----------------------|
| 1          | RESERVA         | Reserva              |
| 2          | CONFIRMACION    | Confirmación de orden|
| 3          | PRODUCCION      | Producción           |
| 4          | ENVIO_MARITIMO  | Envío marítimo       |
| 5          | ADUANA          | Aduana Colombia      |
| 6          | ENTREGA         | Entrega              |

**Lifecycle (lazy seed):** Steps are auto-created on the first GET or PATCH call — NOT on `POST /api/v1/reservations`. This keeps the existing create endpoint untouched. The existing `POST` endpoint does NOT need modification. The unique constraints make this idempotent — duplicate calls will not create duplicate rows. Step names/order are never editable — only `completed`, `completed_date`, and `notes`.

### Existing `reservations` table

No schema changes. The `status` field is kept for compatibility but is no longer the primary UX driver — the timeline replaces it visually.

---

## 2. API

Two new endpoints on the existing FastAPI app:

### `GET /api/v1/reservations/{id}/steps`

Returns the 6 steps for a reservation. Auto-creates them if missing (idempotent). Returns **404** if the reservation itself does not exist.

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

**Datetime handling:** All datetimes are naive UTC (no timezone suffix), consistent with the existing `Reservation` model. The API accepts and returns naive ISO strings (e.g. `"2026-05-09T00:00:00"` — no `Z` suffix).

Returns the updated step object.

**Validation:**
- 404 if reservation not found
- 400 if `step_key` is not one of the 6 valid keys
- If the 6 step rows don't exist yet (e.g., GET was never called), PATCH auto-seeds them first, then applies the update — same idempotent logic as GET.

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

- **Active step** = first step where `completed=false` → highlighted in Tesla blue (#3E6AE1). If all 6 steps are completed, no step is highlighted and a "¡Entrega completada! 🎉" banner replaces the timeline header.
- **Completed steps** → green checkmark + date + notes (if any)
- **Pending steps** → grey, no date
- **Edit form** → inline expander under the active step; any step can be clicked to edit
- **Progress bar** → `completed_count / 6` displayed as `st.progress()` + label
- **Hero card** → shows model, color, RN (canonical source: `reservation.notes` field), order date, current `status`

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
    networks: [tesla-network]

  api:
    build: { context: ., target: production }
    env_file: .env
    volumes: [tesla-data:/app/data]
    healthcheck: (existing)
    networks: [tesla-network]
    # No ports exposed directly — all traffic goes through nginx

  dashboard:
    build: { context: ., target: production }
    env_file: .env
    volumes: [tesla-data:/app/data]
    environment:
      - API_BASE_URL=http://api:8000   # internal Docker network
    command: streamlit run app/dashboard/app.py --server.port=8501 --server.address=0.0.0.0
    depends_on:
      api: { condition: service_healthy }
    networks: [tesla-network]
    # No ports exposed directly — all traffic goes through nginx

  api-dev:
    build: { context: ., target: dev }
    profiles: [dev]
    env_file: .env
    ports: ["8000:8000"]   # exposed for direct access in dev
    volumes: [.:/app, tesla-data:/app/data]
    networks: [tesla-network]
    command: uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

  dashboard-dev:
    build: { context: ., target: dev }
    profiles: [dev]
    env_file: .env
    ports: ["8501:8501"]   # exposed for direct access in dev
    volumes: [.:/app, tesla-data:/app/data]
    environment:
      - API_BASE_URL=http://api-dev:8000   # dev containers share tesla-network
    networks: [tesla-network]
    depends_on: [api-dev]
    command: streamlit run app/dashboard/app.py --server.port=8501 --server.address=0.0.0.0

volumes:
  tesla-data:
networks:
  tesla-network:
    driver: bridge
```

### nginx.conf

File lives at repo root: `nginx.conf` (mounted read-only into nginx container).

```nginx
server {
    listen 80;

    # FastAPI — strip no prefix; routes already start with /api or /health
    location /api/ {
        proxy_pass http://api:8000/api/;
    }
    location /health {
        proxy_pass http://api:8000/health;
    }
    # FastAPI docs — trailing slash redirect handled by proxy
    location /docs {
        proxy_pass http://api:8000/docs;
        proxy_redirect off;
    }
    location /openapi.json {
        proxy_pass http://api:8000/openapi.json;
    }
    # Dashboard — catch-all
    location / {
        proxy_pass http://dashboard:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
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
