# CollectorScheduler - Documentación

## Overview

El `CollectorScheduler` es un sistema de programación automático que ejecuta los collectors de datos (ReservationCollector y ShippingCollector) en intervalos configurados usando APScheduler.

## Características

- **Background Scheduler**: Utiliza APScheduler para ejecutar tareas en background
- **Timezone Support**: Todas las operaciones usan UTC (Coordinated Universal Time)
- **Logging Completo**: Registra inicio, fin, duración y errores de cada ejecución
- **Error Handling**: Captura excepciones sin detener el scheduler
- **Job Management**: Gestiona múltiples jobs de forma automática

## Configuración

### ReservationCollector
- **Intervalo**: Cada 6 horas
- **Job ID**: `reservation_collector`
- **Función**: Recolecta y valida reservas de Tesla

### ShippingCollector
- **Intervalo**: Cada 3 horas
- **Job ID**: `shipping_collector`
- **Función**: Actualiza el estado de envíos y tracking

## Uso

### Opción 1: Usar el scheduler singleton global

```python
from app.collectors.scheduler import initialize_scheduler, shutdown_scheduler

# Iniciar el scheduler
scheduler = initialize_scheduler()

# ... tu aplicación continúa...

# Detener el scheduler al finalizar
shutdown_scheduler()
```

### Opción 2: Crear una instancia específica

```python
from app.collectors.scheduler import CollectorScheduler

# Crear instancia
scheduler = CollectorScheduler()

# Iniciar
scheduler.start_scheduler()

# Obtener estado
status = scheduler.get_job_status()
print(f"Scheduler running: {status['scheduler_running']}")
print(f"Jobs count: {status['jobs_count']}")

# Detener
scheduler.stop_scheduler()
```

### Integracion con FastAPI

```python
from fastapi import FastAPI
from app.collectors.scheduler import initialize_scheduler, shutdown_scheduler

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on app startup."""
    initialize_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown scheduler on app shutdown."""
    shutdown_scheduler()

@app.get("/scheduler/status")
async def get_scheduler_status():
    """Get current scheduler status."""
    from app.collectors.scheduler import get_scheduler
    scheduler = get_scheduler()
    return scheduler.get_job_status()
```

## Métodos Principales

### CollectorScheduler

#### `start_scheduler()`
Inicia el scheduler en background.

```python
scheduler = CollectorScheduler()
scheduler.start_scheduler()
```

#### `stop_scheduler()`
Detiene el scheduler y limpia los recursos.

```python
scheduler.stop_scheduler()
```

#### `add_job_collectors()`
Agrega los jobs de los collectors (llamado automáticamente por `start_scheduler`).

#### `get_job_status()`
Retorna el estado actual de todos los jobs.

```python
status = scheduler.get_job_status()
# {
#     "scheduler_running": True,
#     "jobs_count": 2,
#     "jobs": {
#         "reservation_collector": {
#             "id": "reservation_collector",
#             "name": "Reservation Collector",
#             "next_run_time": "2024-01-15T14:30:00+00:00",
#             "trigger": "interval[0:06:00]",
#             "func_name": "...",
#             "max_instances": 1
#         },
#         "shipping_collector": {...}
#     },
#     "timestamp": "2024-01-15T12:30:00.123456"
# }
```

#### `is_running` (Property)
Retorna si el scheduler está actualmente en ejecución.

```python
if scheduler.is_running:
    print("Scheduler is running")
```

## Funciones Globales

### `get_scheduler()`
Obtiene o crea la instancia global singleton del scheduler.

### `initialize_scheduler()`
Inicializa y inicia el scheduler global singleton.

### `shutdown_scheduler()`
Detiene y limpia la instancia global del scheduler.

## Logging

El scheduler registra todas las operaciones en logs:

```
[INFO] CollectorScheduler started successfully
[INFO] Adding job for reservation collector (interval: 6 hours, job_id: reservation_collector)
[INFO] Successfully added job: reservation_collector
[INFO] [reservation] Collector job started
[INFO] [reservation] Collector job completed successfully. Result: {...}
[INFO] [reservation] Collector job finished. Duration: 0.45s, Success: True
```

## Manejo de Errores

Si un collector falla, el scheduler captura la excepción y continúa ejecutándose:

```python
[ERROR] [reservation] Collector job failed with error: Connection timeout
[ERROR] [reservation] Collector job finished. Duration: 5.23s, Success: False
```

## Timezone

Todas las operaciones usan UTC (Coordinated Universal Time). Los tiempos en la salida de `get_job_status()` siempre están en UTC.

## Testing

Se incluyen tests completos en `tests/test_scheduler.py`:

```bash
python -m pytest tests/test_scheduler.py -v
```

Los tests cubren:
- Inicialización y ciclo de vida del scheduler
- Creación y gestión de jobs
- Manejo de errores y excepciones
- Funciones globales del scheduler
- Configuración de job intervals

## Dependencias

- `APScheduler>=4.0.0`: Framework de programación de tareas
- `pytz>=2026.2`: Soporte de timezones
- `SQLAlchemy>=2.0`: ORM para acceso a base de datos
- `pydantic>=2.0`: Validación de datos

## Notas

1. El scheduler se ejecuta en background, lo que permite que tu aplicación continúe funcionando normalmente.
2. Cada job tiene `max_instances=1`, lo que previene que la misma tarea se ejecute múltiples veces simultáneamente.
3. Los collectors pueden manejar sus propias sesiones de base de datos internamente.
4. El logging usa el módulo estándar `logging` de Python, que se puede configurar globalmente.
