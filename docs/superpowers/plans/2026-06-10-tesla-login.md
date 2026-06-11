# Tesla Login Feature — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir autenticación real con cuenta Tesla via OAuth2 PKCE (teslapy), mostrando datos reales del vehículo en el dashboard Streamlit.

**Architecture:** `TeslaAuthManager` wraps teslapy y persiste tokens en `data/tokens.json`. `app/dashboard/app.py` comprueba sesión al arrancar; si no hay tokens redirige a `app/pages/login.py`. `TeslaCollector` reemplaza los datos mock con datos reales de la Tesla API cuando hay sesión activa.

**Tech Stack:** Python 3.12, teslapy 2.9.1, Streamlit, OAuth2 PKCE (auth.tesla.com), pytest + unittest.mock

---

## Chunk 1: TeslaAuthManager + tests

### Task 1: Instalar teslapy y crear estructura

**Files:**
- Modify: `requirements.txt`
- Create: `app/auth/__init__.py`
- Create: `app/auth/tesla_auth.py`
- Create: `tests/test_tesla_auth.py`

- [ ] **Step 1: Agregar teslapy a requirements.txt**

```
teslapy>=2.7.0
```

Añadir antes de la línea de pytest.

- [ ] **Step 2: Instalar**

```bash
pip install teslapy
```

- [ ] **Step 3: Crear `app/auth/__init__.py` vacío**

```python
```

- [ ] **Step 4: Escribir tests failing para TeslaAuthManager**

Crear `tests/test_tesla_auth.py`:

```python
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from app.auth.tesla_auth import TeslaAuthManager, MFARequiredError


@pytest.fixture
def tmp_token_path(tmp_path):
    return str(tmp_path / "tokens.json")


class TestHasValidSession:
    def test_returns_false_when_no_cache_file(self, tmp_token_path):
        auth = TeslaAuthManager(tmp_token_path)
        assert auth.has_valid_session() is False

    def test_returns_false_when_cache_empty(self, tmp_token_path):
        with open(tmp_token_path, "w") as f:
            json.dump({}, f)
        auth = TeslaAuthManager(tmp_token_path)
        assert auth.has_valid_session() is False

    def test_returns_true_when_tesla_authorized(self, tmp_token_path):
        cache = {"user@example.com": {"access_token": "tok", "token_type": "Bearer"}}
        with open(tmp_token_path, "w") as f:
            json.dump(cache, f)
        with patch("teslapy.Tesla") as MockTesla:
            instance = MagicMock()
            instance.authorized = True
            MockTesla.return_value = instance
            auth = TeslaAuthManager(tmp_token_path)
            assert auth.has_valid_session() is True


class TestStartAuth:
    def test_returns_url_state_verifier(self, tmp_token_path):
        with patch("teslapy.Tesla") as MockTesla:
            instance = MagicMock()
            instance.new_state.return_value = "state123"
            instance.new_code_verifier.return_value = "verifier456"
            instance.authorization_url.return_value = "https://auth.tesla.com/oauth2/..."
            MockTesla.return_value = instance
            auth = TeslaAuthManager(tmp_token_path)
            url, state, cv = auth.start_auth("user@example.com")
            assert url.startswith("https://")
            assert state == "state123"
            assert cv == "verifier456"


class TestCompleteAuth:
    def test_returns_true_on_success(self, tmp_token_path):
        with patch("teslapy.Tesla") as MockTesla:
            instance = MagicMock()
            instance.authorized = True
            MockTesla.return_value = instance
            auth = TeslaAuthManager(tmp_token_path)
            result = auth.complete_auth(
                "user@example.com",
                "https://auth.tesla.com/void/callback?code=abc&state=state123",
                "state123",
                "verifier456",
            )
            assert result is True
            instance.fetch_token.assert_called_once()

    def test_returns_false_on_failure(self, tmp_token_path):
        with patch("teslapy.Tesla") as MockTesla:
            instance = MagicMock()
            instance.authorized = False
            MockTesla.return_value = instance
            auth = TeslaAuthManager(tmp_token_path)
            result = auth.complete_auth("user@example.com", "bad_url", "s", "v")
            assert result is False


class TestLogout:
    def test_removes_token_file(self, tmp_token_path):
        with open(tmp_token_path, "w") as f:
            json.dump({"email": {}}, f)
        auth = TeslaAuthManager(tmp_token_path)
        auth.logout()
        assert not os.path.exists(tmp_token_path)

    def test_noop_when_no_file(self, tmp_token_path):
        auth = TeslaAuthManager(tmp_token_path)
        auth.logout()  # must not raise
```

- [ ] **Step 5: Correr tests — deben fallar con ImportError**

```bash
pytest tests/test_tesla_auth.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'TeslaAuthManager'`

- [ ] **Step 6: Implementar `app/auth/tesla_auth.py`**

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

    def has_valid_session(self) -> bool:
        if not os.path.exists(self._token_path):
            return False
        email = self._get_cached_email()
        if not email:
            return False
        try:
            tesla = teslapy.Tesla(email, cache_file=self._token_path)
            return bool(tesla.authorized)
        except Exception:
            return False

    def start_auth(self, email: str) -> Tuple[str, str, str]:
        """Start OAuth2 PKCE flow. Returns (auth_url, state, code_verifier)."""
        os.makedirs(os.path.dirname(os.path.abspath(self._token_path)), exist_ok=True)
        tesla = teslapy.Tesla(email, cache_file=self._token_path)
        state = tesla.new_state()
        code_verifier = tesla.new_code_verifier()
        auth_url = tesla.authorization_url(state=state, code_verifier=code_verifier)
        return auth_url, state, code_verifier

    def complete_auth(
        self, email: str, callback_url: str, state: str, code_verifier: str
    ) -> bool:
        """Complete OAuth2 PKCE flow. Returns True on success."""
        tesla = teslapy.Tesla(email, cache_file=self._token_path)
        try:
            tesla.fetch_token(
                authorization_response=callback_url,
                state=state,
                code_verifier=code_verifier,
            )
        except Exception:
            return False
        return bool(tesla.authorized)

    def get_tesla_client(self) -> teslapy.Tesla:
        email = self._get_cached_email()
        if not email:
            raise RuntimeError("No hay sesión activa — tokens no encontrados")
        return teslapy.Tesla(email, cache_file=self._token_path)

    def logout(self) -> None:
        if os.path.exists(self._token_path):
            os.remove(self._token_path)

    def _get_cached_email(self) -> Optional[str]:
        try:
            with open(self._token_path) as f:
                cache = json.load(f)
            if cache:
                return next(iter(cache))
        except Exception:
            pass
        return None
```

- [ ] **Step 7: Correr tests — deben pasar**

```bash
pytest tests/test_tesla_auth.py -v
```

Expected: `9 passed`

- [ ] **Step 8: Commit**

```bash
git add app/auth/ tests/test_tesla_auth.py requirements.txt
git commit -m "feat: add TeslaAuthManager with OAuth2 PKCE flow"
```

---

## Chunk 2: TeslaCollector + tests

### Task 2: TeslaCollector — mapea vehículos Tesla a schema interno

**Files:**
- Create: `app/collectors/tesla.py`
- Create: `tests/test_tesla_collector.py`

- [ ] **Step 1: Escribir tests failing**

Crear `tests/test_tesla_collector.py`:

```python
import pytest
from unittest.mock import MagicMock
from app.collectors.tesla import TeslaCollector
from app.auth.tesla_auth import TeslaAuthManager


@pytest.fixture
def mock_auth():
    auth = MagicMock(spec=TeslaAuthManager)
    mock_tesla = MagicMock()
    auth.get_tesla_client.return_value = mock_tesla
    return auth, mock_tesla


class TestFetchReservations:
    def test_returns_list_of_dicts(self, mock_auth):
        auth, mock_tesla = mock_auth
        mock_tesla.vehicle_list.return_value = [
            {
                "vin": "5YJ3E1EA1KF000001",
                "display_name": "Mi Tesla",
                "state": "online",
                "vehicle_config": {"car_type": "model3", "exterior_color": "SolidBlack"},
            }
        ]
        collector = TeslaCollector(auth)
        result = collector.fetch_reservations()
        assert len(result) == 1
        assert result[0]["vin"] == "5YJ3E1EA1KF000001"
        assert result[0]["model"] == "Model 3"
        assert result[0]["status"] == "DELIVERED"

    def test_empty_vehicle_list(self, mock_auth):
        auth, mock_tesla = mock_auth
        mock_tesla.vehicle_list.return_value = []
        collector = TeslaCollector(auth)
        assert collector.fetch_reservations() == []


class TestStatusMapping:
    @pytest.mark.parametrize("tesla_state,expected", [
        ("new", "CONFIRMED"),
        ("factory", "MANUFACTURING"),
        ("transit", "IN_TRANSIT"),
        ("delivered", "DELIVERED"),
        ("online", "DELIVERED"),
        ("unknown_state", "RESERVED"),
        ("", "RESERVED"),
    ])
    def test_status_map(self, tesla_state, expected, mock_auth):
        auth, mock_tesla = mock_auth
        mock_tesla.vehicle_list.return_value = [
            {"vin": "VIN1", "display_name": "X", "state": tesla_state, "vehicle_config": {}}
        ]
        collector = TeslaCollector(auth)
        result = collector.fetch_reservations()
        assert result[0]["status"] == expected


class TestModelMapping:
    @pytest.mark.parametrize("car_type,expected_model", [
        ("model3", "Model 3"),
        ("modely", "Model Y"),
        ("modelx", "Model X"),
        ("models", "Model S"),
        ("unknown", "unknown"),
    ])
    def test_model_map(self, car_type, expected_model, mock_auth):
        auth, mock_tesla = mock_auth
        mock_tesla.vehicle_list.return_value = [
            {"vin": "V", "display_name": "T", "state": "online",
             "vehicle_config": {"car_type": car_type}}
        ]
        collector = TeslaCollector(auth)
        result = collector.fetch_reservations()
        assert result[0]["model"] == expected_model
```

- [ ] **Step 2: Correr tests — deben fallar con ImportError**

```bash
pytest tests/test_tesla_collector.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implementar `app/collectors/tesla.py`**

```python
from app.auth.tesla_auth import TeslaAuthManager


class TeslaCollector:
    STATUS_MAP = {
        "new": "CONFIRMED",
        "factory": "MANUFACTURING",
        "transit": "IN_TRANSIT",
        "delivered": "DELIVERED",
        "online": "DELIVERED",
    }
    MODEL_MAP = {
        "model3": "Model 3",
        "modely": "Model Y",
        "modelx": "Model X",
        "models": "Model S",
    }

    def __init__(self, auth: TeslaAuthManager):
        self._tesla = auth.get_tesla_client()

    def fetch_reservations(self) -> list:
        return [self._map_vehicle(v) for v in self._tesla.vehicle_list()]

    def _map_vehicle(self, v: dict) -> dict:
        cfg = v.get("vehicle_config", {})
        car_type = cfg.get("car_type", "")
        return {
            "vin": v.get("vin"),
            "model": self.MODEL_MAP.get(car_type.lower(), car_type),
            "color": cfg.get("exterior_color", ""),
            "status": self.STATUS_MAP.get(v.get("state", ""), "RESERVED"),
            "notes": v.get("display_name", ""),
        }
```

- [ ] **Step 4: Correr tests — deben pasar**

```bash
pytest tests/test_tesla_collector.py -v
```

Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add app/collectors/tesla.py tests/test_tesla_collector.py
git commit -m "feat: add TeslaCollector mapping Tesla vehicles to internal schema"
```

---

## Chunk 3: Login page + integración en dashboard

### Task 3: Login page Streamlit

**Files:**
- Create: `app/pages/__init__.py`
- Create: `app/pages/login.py`

- [ ] **Step 1: Crear `app/pages/__init__.py` vacío**

```python
```

- [ ] **Step 2: Crear `app/pages/login.py`**

```python
import streamlit as st
from app.auth.tesla_auth import TeslaAuthManager


def render_login(auth: TeslaAuthManager) -> None:
    st.markdown(
        """
        <div style='text-align:center;padding:60px 0 20px'>
            <h1>🚗 Tesla Tracker</h1>
            <p style='color:#6b7280'>Conecta tu cuenta Tesla para ver el estado de tu orden</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        step = st.session_state.get("auth_step", "start")

        if step == "start":
            with st.form("tesla_start"):
                email = st.text_input("Email de tu cuenta Tesla")
                submitted = st.form_submit_button(
                    "Generar enlace de Tesla", use_container_width=True
                )
            if submitted:
                if not email:
                    st.error("Introduce tu email de Tesla")
                else:
                    try:
                        auth_url, state, cv = auth.start_auth(email)
                        st.session_state.auth_email = email
                        st.session_state.auth_state = state
                        st.session_state.auth_cv = cv
                        st.session_state.auth_url = auth_url
                        st.session_state.auth_step = "callback"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al generar enlace: {e}")

        elif step == "callback":
            st.info(
                "**Paso 1:** Haz clic en el enlace de abajo y autentícate en Tesla.  \n"
                "**Paso 2:** Después de autenticarte, copia la URL de la página de retorno "
                "(empieza con `https://auth.tesla.com/void/callback?...`) y pégala aquí."
            )
            st.link_button(
                "🔗 Abrir autenticación Tesla",
                st.session_state.auth_url,
                use_container_width=True,
            )
            st.divider()
            with st.form("tesla_callback"):
                callback = st.text_input(
                    "URL de retorno",
                    placeholder="https://auth.tesla.com/void/callback?code=...&state=...",
                )
                col_ok, col_back = st.columns(2)
                with col_ok:
                    submitted = st.form_submit_button(
                        "Completar autenticación", use_container_width=True
                    )
                with col_back:
                    back = st.form_submit_button(
                        "← Volver", use_container_width=True
                    )
            if back:
                for k in ("auth_step", "auth_email", "auth_state", "auth_cv", "auth_url"):
                    st.session_state.pop(k, None)
                st.rerun()
            if submitted:
                if not callback:
                    st.error("Pega la URL de retorno")
                else:
                    with st.spinner("Verificando..."):
                        try:
                            ok = auth.complete_auth(
                                st.session_state.auth_email,
                                callback,
                                st.session_state.auth_state,
                                st.session_state.auth_cv,
                            )
                        except Exception as e:
                            st.error(f"Error: {e}")
                            ok = False
                    if ok:
                        st.success("✅ ¡Autenticado! Cargando dashboard...")
                        st.session_state.auth_step = "done"
                        st.rerun()
                    else:
                        st.error(
                            "Autenticación fallida. Verifica que la URL sea correcta."
                        )
```

- [ ] **Step 3: Commit**

```bash
git add app/pages/
git commit -m "feat: add Tesla OAuth2 login page for Streamlit"
```

---

### Task 4: Integrar auth en `app/dashboard/app.py`

**Files:**
- Modify: `app/dashboard/app.py` (inicio del archivo, ~líneas 1-20)
- Modify: `.gitignore`

- [ ] **Step 1: Agregar `data/tokens.json` a `.gitignore`**

En `.gitignore`, añadir debajo de `data/*.db`:
```
data/tokens.json
```

- [ ] **Step 2: Añadir auth check al inicio de `app/dashboard/app.py`**

Después de los imports y `st.set_page_config(...)`, antes de cualquier otra lógica, insertar:

```python
from app.auth.tesla_auth import TeslaAuthManager

_auth = TeslaAuthManager()
if not _auth.has_valid_session():
    from app.pages.login import render_login
    render_login(_auth)
    st.stop()
```

- [ ] **Step 3: Añadir botón logout en sidebar**

En la función `main()` o en el bloque de sidebar, al final:

```python
st.sidebar.divider()
if st.sidebar.button("🔓 Cerrar sesión Tesla", use_container_width=True):
    _auth.logout()
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()
```

- [ ] **Step 4: Añadir banner de sesión activa en sidebar**

Justo después del auth check:

```python
cached_email = _auth._get_cached_email()
st.sidebar.success(f"✅ Tesla: {cached_email or 'conectado'}")
```

- [ ] **Step 5: Correr la suite completa de tests**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: todos los tests previos + los nuevos pasan. No regresiones.

- [ ] **Step 6: Commit final**

```bash
git add app/dashboard/app.py .gitignore
git commit -m "feat: integrate Tesla auth into dashboard — redirect to login when no session"
```

---

## Verificación manual

Después de todos los commits:

```bash
# Terminal 1
uvicorn app.api.main:app --port 8000

# Terminal 2
streamlit run app/dashboard/app.py
```

Abrir `http://localhost:8501` — debe mostrar la pantalla de login.
Hacer clic en "Generar enlace de Tesla", seguir flujo OAuth2.
Tras autenticarse, el dashboard debe cargar con el banner "✅ Tesla: email@...".
El botón "Cerrar sesión" debe redirigir de vuelta al login.
