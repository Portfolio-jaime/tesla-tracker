# Tesla Tracker — Diseño de Mejoras

**Fecha:** 2026-06-07  
**Estado:** Aprobado  
**Repositorio:** `tesla-tracker`

---

## Contexto

La app tiene una base funcional (FastAPI + SQLite + Streamlit dashboard + collectors + scheduler) pero con tres problemas bloqueantes en tests y cuatro áreas de mejora acordadas con el usuario.

---

## Alcance

1. Fix de tests (3 blockers)
2. Modelo de estados unificado
3. Dashboard mejorado en Streamlit
4. Collectors configurables + Alertas Telegram funcionales

---

## Sección 1: Fix de Tests

### Problemas

| Archivo | Error | Causa raíz |
|---|---|---|
| `tests/test_api.py` | `OperationalError: unable to open database file` | `Base.metadata.create_all()` corre a nivel módulo en `app/api/main.py` antes de que exista el directorio `data/` |
| `tests/test_collectors.py` | `SyntaxError: unicode error 0xdc` | Byte corrupto en línea 123 — carácter `Ü` mal codificado |
| `tests/test_scheduler.py` | `ModuleNotFoundError: No module named 'apscheduler'` | Paquete en `requirements.txt` pero no instalado en el entorno |

### Fixes

- **`app/api/main.py`**: Mover `Base.metadata.create_all()` a un lifespan event de FastAPI. Crear el directorio `data/` programáticamente si no existe antes de abrir la conexión.
- **`tests/test_collectors.py` línea 123**: Reemplazar el byte corrupto por `"19-inch Überturbine"`.
- **Entorno**: Instalar `apscheduler` con `pip install apscheduler`.
- **Bonus**: Corregir las deprecation warnings de Pydantic V2 en `app/core/config.py` y `app/database/schemas.py` — cambiar `class Config` por `model_config = ConfigDict(...)`.

---

## Sección 2: Modelo de Estados Unificado

### Estado actual (inconsistente)

- API / DB: `RESERVED, BOOKED, PENDING_VIN, IN_TRANSIT, DELIVERED`
- `ShippingCollector`: `RESERVED, CONFIRMED, MANUFACTURING, QUALITY_CHECK, SHIPPING, IN_TRANSIT, DELIVERED, CANCELLED`

### Estado objetivo (fuente de verdad única)

```
RESERVED → CONFIRMED → MANUFACTURING → QUALITY_CHECK → SHIPPING → IN_TRANSIT → DELIVERED
                                                                              ↘ CANCELLED
```

### Cambios requeridos

- `app/database/schemas.py`: Agregar validación `Literal[...]` en el campo `status` de `ReservationBase` con los 8 estados válidos.
- `app/api/main.py` — endpoint `/api/v1/stats`: Reemplazar los estados hardcodeados (`BOOKED`, `PENDING_VIN`) por los del nuevo vocabulario.
- `app/database/init_db.py`: Actualizar seeds para usar los nuevos estados.
- `app/collectors/reservation.py` — datos simulados: Ajustar los mocks para usar estados válidos (`CONFIRMED`, `MANUFACTURING`, etc.).
- `tests/test_api.py`: Actualizar los tests que usan `BOOKED` → `CONFIRMED`.

---

## Sección 3: Dashboard Mejorado (Streamlit)

### Componentes nuevos en `app/dashboard/app.py`

**KPIs globales (parte superior)**
- Total de reservas
- Vehículos en tránsito (`IN_TRANSIT` + `SHIPPING`)
- Vehículos entregados (`DELIVERED`)
- Próxima entrega estimada (menor `eta_end` de reservas activas)

**Timeline visual de estados**
- Barra de progreso horizontal con los 7 estados del ciclo de vida
- El estado actual del vehículo seleccionado queda resaltado
- Implementado con `st.progress()` + columnas de Streamlit

**Vista de detalle por reserva**
- Selector de reserva en sidebar (por modelo + VIN parcial)
- Muestra: estado actual con timeline, ETA en días restantes, fechas de creación y última actualización

**Gráfica de distribución**
- Pie chart Plotly de reservas por estado
- Ya disponible via `plotly` en `requirements.txt`

### Arquitectura

Sin cambios: el dashboard continúa leyendo directo de SQLite via `SessionLocal`. No pasa por la API REST.

---

## Sección 4: Collectors Configurables + Alertas Telegram

### Collectors configurables

**Objetivo**: Reemplazar datos hardcodeados en `ReservationCollector.fetch_reservations()` por datos leídos desde variables de entorno.

**Variables de entorno nuevas** (en `.env.example`):
```ini
TESLA_VIN=5YJ3E1EA1KF000000
TESLA_MODEL=Model 3
TESLA_COLOR=Midnight Black
TESLA_STATUS=IN_TRANSIT
TESLA_ETA_START=2026-07-01
TESLA_ETA_END=2026-07-15
```

**Comportamiento**:
- Si las variables están configuradas → usa esos datos como reserva principal
- Si no están configuradas → usa el set de datos de ejemplo hardcodeado (fallback, para que la app funcione sin config)

**Cambios**: `app/core/config.py` agrega los nuevos campos opcionales. `ReservationCollector.fetch_reservations()` lee de `get_settings()`.

### Alertas Telegram funcionales

**Objetivo**: Conectar `TelegramAlert` al flujo de `ShippingCollector.update_reservations()`.

**Trigger**: Cuando el status de una reserva cambia (old_status ≠ new_status), se llama `TelegramAlert.send()`.

**Mensaje de alerta**:
```
🚗 Model 3 (VIN: 5YJ3E1EA...)
Estado actualizado: IN_TRANSIT → DELIVERED
📅 Entrega confirmada
```

**Comportamiento seguro**:
- Si `TELEGRAM_BOT_TOKEN` o `TELEGRAM_CHAT_ID` están vacíos → loguea la alerta y continúa sin error
- La alerta nunca bloquea ni falla el flujo principal de actualización

**Cambios**: `app/alerts/telegram.py` implementa el envío real via `requests.post()`. `app/collectors/shipping.py` importa y llama `TelegramAlert` en `update_reservations()`.

---

## Orden de implementación

1. Instalar dependencias faltantes (`apscheduler`)
2. Fix unicode en `test_collectors.py`
3. Refactorizar `app/api/main.py` (lifespan + crear `data/`)
4. Corregir deprecation warnings Pydantic V2
5. Unificar modelo de estados (schemas + API + seeds + mocks + tests)
6. Mejorar dashboard Streamlit
7. Hacer collectors configurables via env vars
8. Conectar alertas Telegram

---

## Archivos afectados

| Archivo | Tipo de cambio |
|---|---|
| `app/api/main.py` | Refactor lifespan, fix stats endpoint |
| `app/core/config.py` | Pydantic V2 + nuevas env vars Tesla |
| `app/database/schemas.py` | Pydantic V2 + Literal status |
| `app/database/init_db.py` | Seeds con estados correctos |
| `app/collectors/reservation.py` | Fetch desde env vars |
| `app/collectors/shipping.py` | Integración alertas Telegram |
| `app/alerts/telegram.py` | Implementación real del envío |
| `app/dashboard/app.py` | KPIs + timeline + detalle + gráfica |
| `tests/test_api.py` | Actualizar estados en tests |
| `tests/test_collectors.py` | Fix unicode |
| `.env.example` | Nuevas variables Tesla |
| `requirements.txt` | Confirmar que `apscheduler` queda instalado (ya está declarado) |
