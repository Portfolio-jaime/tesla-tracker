# Tesla Fleet API Migration — Diseño

**Fecha:** 2026-06-11
**Estado:** Aprobado
**Repositorio:** `tesla-tracker`

---

## Contexto

Tesla deprecó `client_id=ownerapi` (usado por `teslapy`) para nuevas autenticaciones. El flujo OAuth2 actual lanza `"redirect_uri not registered for this client_id"`. La solución es migrar a la Fleet API oficial, que requiere registrar una aplicación con una clave pública EC alojada en un dominio público.

---

## Arquitectura

### Fase 1 — Setup one-time (manual, fuera del código)

1. Generar un par de claves EC (ES256) localmente
2. Publicar la clave pública en GitHub Pages en la ruta requerida por Tesla
3. Registrar la app en `developer.tesla.com` (nombre, dominio, URL de clave pública)
4. Obtener el `client_id` asignado por Tesla
5. Agregar `TESLA_CLIENT_ID=<valor>` al archivo `.env`

### Fase 2 — Cambios en el código (~20 líneas)

El flujo OAuth2 PKCE es idéntico al actual. Solo cambia el `client_id` que `teslapy` usa para construir la URL de autorización.

```
.env → Settings.TESLA_CLIENT_ID → TeslaAuthManager.__init__ → teslapy.SSO_CLIENT_ID (monkey-patch)
```

---

## Archivos afectados

| Archivo | Cambio |
|---|---|
| `app/core/config.py` | Agregar campo `TESLA_CLIENT_ID: str = ""` a `Settings` |
| `app/auth/tesla_auth.py` | Monkey-patch `teslapy.SSO_CLIENT_ID` en `__init__` si `TESLA_CLIENT_ID` está configurado |
| `.env.example` | Agregar `TESLA_CLIENT_ID=` con comentario explicativo |

---

## Detalle de implementación

### `app/core/config.py`

```python
class Settings(BaseSettings):
    # ... existing fields ...
    TESLA_CLIENT_ID: str = ""
```

### `app/auth/tesla_auth.py`

```python
import teslapy
from app.core.config import get_settings

class TeslaAuthManager:
    def __init__(self, token_path: str = DEFAULT_TOKEN_PATH):
        self._token_path = token_path
        settings = get_settings()
        if settings.TESLA_CLIENT_ID:
            teslapy.SSO_CLIENT_ID = settings.TESLA_CLIENT_ID
```

### `.env.example`

```
# Tesla Fleet API — obtener en developer.tesla.com
TESLA_CLIENT_ID=
```

---

## Setup one-time: GitHub Pages

La clave pública debe estar accesible en:
```
https://<usuario>.github.io/.well-known/appspecific/com.tesla.3p.public-key.pem
```

Pasos:
1. Crear repo `<usuario>.github.io` (o repo con Pages habilitado)
2. Crear carpeta `.well-known/appspecific/`
3. Subir `com.tesla.3p.public-key.pem` (clave pública EC)
4. Verificar que la URL es accesible públicamente

Comando para generar el par de claves:
```bash
openssl ecparam -name prime256v1 -genkey -noout -out private.pem
openssl ec -in private.pem -pubout -out com.tesla.3p.public-key.pem
```

---

## Registro en developer.tesla.com

En el formulario de registro:
- **App name**: Tesla Tracker (o similar)
- **Domain**: `https://<usuario>.github.io`
- **Allowed origins**: `https://<usuario>.github.io`
- **Redirect URIs**: `https://auth.tesla.com/void/callback`

Tesla asignará un `client_id` que se agrega a `.env`.

---

## Error Handling

| Escenario | Comportamiento |
|---|---|
| `TESLA_CLIENT_ID` vacío | Usa el client_id por defecto de teslapy (mostrará el error previo) |
| App no aprobada aún | Tesla muestra error en la página de auth |
| Clave pública no accesible | Registro en developer.tesla.com fallará antes de llegar al código |

---

## Tests

Los tests existentes (`tests/test_tesla_auth.py`) no requieren cambios. El monkey-patch ocurre en `__init__`, que el mock de teslapy ya intercepta. Se agrega 1 test nuevo:

```python
def test_patches_sso_client_id_when_configured(monkeypatch):
    monkeypatch.setenv("TESLA_CLIENT_ID", "my-fleet-client")
    auth = TeslaAuthManager()
    import teslapy
    assert teslapy.SSO_CLIENT_ID == "my-fleet-client"
```

---

## Dependencias

Sin cambios en `requirements.txt`. Se reutiliza `teslapy>=2.7.0` ya instalado.
