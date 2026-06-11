# Tesla Fleet API Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hacer que `TeslaAuthManager` use el `client_id` de la Fleet API (configurado via env var) en lugar del deprecated `ownerapi` hardcodeado en teslapy.

**Architecture:** Se agrega `TESLA_CLIENT_ID` a `Settings` (pydantic-settings). `TeslaAuthManager.__init__` lee ese valor y monkey-patchea `teslapy.SSO_CLIENT_ID` si está configurado. El flujo OAuth2 PKCE existente no cambia.

**Tech Stack:** Python 3.12, pydantic-settings, teslapy 2.9.1, pytest

---

## Chunk 1: Settings + patch + test

### Task 1: Agregar `TESLA_CLIENT_ID` a Settings

**Files:**
- Modify: `app/core/config.py:6-27`
- Test: `tests/test_fleet_api.py` (nuevo)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_fleet_api.py`:

```python
import pytest
from unittest.mock import patch


def test_tesla_client_id_default_is_empty():
    """Settings must expose TESLA_CLIENT_ID with empty default."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert hasattr(s, "TESLA_CLIENT_ID")
    assert s.TESLA_CLIENT_ID == ""
    get_settings.cache_clear()
```

- [ ] **Step 2: Verificar que falla**

```bash
.venv/bin/pytest tests/test_fleet_api.py::test_tesla_client_id_default_is_empty -v
```

Expected: `FAILED` — `AttributeError: 'Settings' object has no attribute 'TESLA_CLIENT_ID'`

- [ ] **Step 3: Implementar — agregar campo a Settings**

En `app/core/config.py`, agregar al final del bloque de campos de `Settings` (después de `TESLA_ETA_END`):

```python
    # Tesla Fleet API client_id — obtener en developer.tesla.com
    TESLA_CLIENT_ID: str = ""
```

El archivo completo queda:

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

    TESLA_VIN: str = ""
    TESLA_MODEL: str = ""
    TESLA_COLOR: str = ""
    TESLA_STATUS: str = "RESERVED"
    TESLA_ETA_START: str = ""
    TESLA_ETA_END: str = ""

    # Tesla Fleet API client_id — obtener en developer.tesla.com
    TESLA_CLIENT_ID: str = ""


@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Verificar que pasa**

```bash
.venv/bin/pytest tests/test_fleet_api.py::test_tesla_client_id_default_is_empty -v
```

Expected: `PASSED`

---

### Task 2: Monkey-patch en `TeslaAuthManager.__init__`

**Files:**
- Modify: `app/auth/tesla_auth.py:12-17`
- Test: `tests/test_fleet_api.py` (agregar test)

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_fleet_api.py`:

```python
def test_patches_sso_client_id_when_configured(monkeypatch):
    """TeslaAuthManager must patch teslapy.SSO_CLIENT_ID if TESLA_CLIENT_ID is set."""
    import teslapy
    # setattr registra el valor original con pytest — restauración garantizada aunque el test falle
    monkeypatch.setattr(teslapy, "SSO_CLIENT_ID", teslapy.SSO_CLIENT_ID)
    monkeypatch.setenv("TESLA_CLIENT_ID", "my-fleet-client-id")
    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.auth.tesla_auth import TeslaAuthManager
    TeslaAuthManager()  # __init__ debe parchear el global

    assert teslapy.SSO_CLIENT_ID == "my-fleet-client-id"
    get_settings.cache_clear()  # limpiar cache de settings para tests posteriores
```

- [ ] **Step 2: Verificar que falla**

```bash
.venv/bin/pytest tests/test_fleet_api.py::test_patches_sso_client_id_when_configured -v
```

Expected: `FAILED` — `AssertionError: assert 'ownerapi' == 'my-fleet-client-id'`

- [ ] **Step 3: Implementar — agregar patch en `__init__`**

En `app/auth/tesla_auth.py`, modificar `__init__`:

```python
import json
import os
from typing import Optional, Tuple

import teslapy


class MFARequiredError(Exception):
    pass


class TeslaAuthManager:
    DEFAULT_TOKEN_PATH = "data/tokens.json"

    def __init__(self, token_path: str = DEFAULT_TOKEN_PATH):
        self._token_path = token_path
        from app.core.config import get_settings
        client_id = get_settings().TESLA_CLIENT_ID
        if client_id:
            teslapy.SSO_CLIENT_ID = client_id
```

El resto del archivo (`has_valid_session`, `start_auth`, etc.) no cambia.

- [ ] **Step 4: Verificar que pasa**

```bash
.venv/bin/pytest tests/test_fleet_api.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Verificar que los tests existentes siguen pasando**

```bash
.venv/bin/pytest tests/test_tesla_auth.py tests/test_tesla_collector.py -v
```

Expected: `22 passed`

---

### Task 3: Actualizar `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Agregar la nueva variable**

Abrir `.env.example` y agregar al final:

```
# Tesla Fleet API — registrar app en developer.tesla.com para obtener el client_id
TESLA_CLIENT_ID=
```

No hay test para este paso (es solo documentación de configuración).

---

### Task 4: Commit final

- [ ] **Step 1: Commit**

```bash
git add app/core/config.py app/auth/tesla_auth.py tests/test_fleet_api.py .env.example
git commit -m "feat: read TESLA_CLIENT_ID from env and patch teslapy.SSO_CLIENT_ID"
```

---

## Setup one-time (manual — fuera del código)

Estos pasos los ejecuta el usuario, no el agente. Se documentan aquí como referencia.

### Generar el par de claves EC

```bash
openssl ecparam -name prime256v1 -genkey -noout -out private.pem
openssl ec -in private.pem -pubout -out com.tesla.3p.public-key.pem
```

> **Importante:** `private.pem` no se sube al repo. Agregar a `.gitignore` si no está ya.

### Publicar en GitHub Pages

1. Crear un repo GitHub Pages (`<usuario>.github.io` o cualquier repo con Pages activado)
2. Crear la carpeta `.well-known/appspecific/` en la raíz del repo
3. Subir `com.tesla.3p.public-key.pem` a esa carpeta
4. Verificar que `https://<usuario>.github.io/.well-known/appspecific/com.tesla.3p.public-key.pem` es accesible

### Registrar en developer.tesla.com

1. Ir a `https://developer.tesla.com/` e iniciar sesión con la cuenta Tesla
2. Crear una nueva aplicación:
   - **App name**: Tesla Tracker
   - **Domain**: `https://<usuario>.github.io`
   - **Allowed origins**: `https://<usuario>.github.io`
   - **Redirect URIs**: `https://auth.tesla.com/void/callback`
3. Tesla asignará un `client_id`
4. Agregar al `.env` local: `TESLA_CLIENT_ID=<valor>`
