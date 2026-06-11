# Tesla Login Feature — Diseño

**Fecha:** 2026-06-10
**Estado:** Aprobado
**Repositorio:** `tesla-tracker`

---

## Contexto

La app actualmente usa datos mock o variables de entorno TESLA_*. El objetivo es permitir autenticación real con cuenta Tesla vía OAuth2 (teslapy), mostrando datos reales del vehículo en el dashboard.

---

## Arquitectura

### Archivos nuevos (4)
- `app/auth/tesla_auth.py` — `TeslaAuthManager`: wraps teslapy, lee/escribe tokens
- `app/pages/login.py` — pantalla de login Streamlit (página completa cuando no hay sesión)
- `app/collectors/tesla.py` — `TeslaCollector`: llama Tesla API, reemplaza mocks
- `data/tokens.json` — storage de tokens (runtime, gitignored)

### Archivos modificados (2)
- `app/dashboard/app.py` — comprueba tokens al arrancar; si no hay sesión → muestra login
- `.gitignore` — agrega `data/tokens.json`

### Flujo
```
app.py arranca → TeslaAuthManager.has_valid_session()?
  NO  → render_login() → email+pass → teslapy OAuth2 → tokens.json → st.rerun()
  SÍ  → TeslaCollector.fetch_reservations() → datos reales en dashboard
```

---

## Sección 1: TeslaAuthManager (`app/auth/tesla_auth.py`)

```python
class TeslaAuthManager:
    def __init__(self, token_path: str = "data/tokens.json")
    def has_valid_session(self) -> bool        # comprueba tokens.json
    def authenticate(self, email, password, mfa_code="") -> bool  # OAuth2; lanza MFARequiredError si hace falta
    def get_vehicles(self) -> list[dict]
    def logout(self) -> None                   # elimina tokens.json
    def get_tesla_client(self) -> teslapy.Tesla

class MFARequiredError(Exception): pass
```

**Token persistence:** `teslapy.Tesla(email, cache_file=token_path)` — auto-refresh al expirar.

---

## Sección 2: Login Page (`app/pages/login.py`)

Máquina de estados en `st.session_state.auth_step`:
- `"login"` → form email + password
- `"mfa"` → form código MFA (si Tesla requiere 2FA)
- `"authenticated"` → no renderiza; app.py detecta sesión y sigue

**Integración en `app/dashboard/app.py`:**
```python
auth = TeslaAuthManager()
if not auth.has_valid_session():
    from app.pages.login import render_login
    render_login(auth)
    st.stop()
```

---

## Sección 3: TeslaCollector (`app/collectors/tesla.py`)

```python
class TeslaCollector:
    def fetch_reservations(self) -> list[dict]   # llama vehicle_list(), mapea a schema interno
    def _map_vehicle(self, v) -> dict
    def _map_status(self, state) -> str
```

**Mapeo de estados:**
| Tesla `state` | Interno |
|---|---|
| `"new"` | `CONFIRMED` |
| `"factory"` | `MANUFACTURING` |
| `"transit"` | `IN_TRANSIT` |
| `"delivered"` / `"online"` | `DELIVERED` |
| desconocido | `RESERVED` |

---

## Sección 4: Error Handling

| Escenario | Comportamiento |
|---|---|
| Token expirado | teslapy auto-refresca; si falla → logout + redirect login |
| MFA requerido | Flujo 2 pasos en login page |
| API Tesla no disponible | `st.warning()` + carga datos desde DB |
| Credenciales inválidas | `st.error("Email o contraseña incorrectos")` |
| `tokens.json` corrupto | Eliminar + redirect login |

---

## Dependencias nuevas

```
teslapy>=2.7.0
```

Agregar a `requirements.txt`.
