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
        if not st.session_state.get("_balloons_shown"):
            st.session_state["_balloons_shown"] = True
            st.balloons()

    active_step = next((s for s in steps if not s["completed"]), None)

    for step in steps:
        label = STEP_LABELS.get(step["step_key"], step["step_key"])
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
    st.info("No tienes vehículos registrados aún.")
    with st.expander("➕ Agregar mi reserva / orden Tesla", expanded=True):
        with st.form("add_reservation"):
            col1, col2 = st.columns(2)
            with col1:
                model = st.selectbox("Modelo", ["Model Y", "Model 3", "Model S", "Model X", "Cybertruck"])
                color = st.text_input("Color", placeholder="Pearl White, Midnight Silver...")
            with col2:
                status = st.selectbox("Estado actual", ["RESERVED", "CONFIRMED", "MANUFACTURING", "IN_TRANSIT", "DELIVERED"])
                order_date = st.date_input("Fecha de orden")
            notes = st.text_input("Notas (referencia, configuración...)", placeholder="Ej: Configuración premium, 7 asientos")
            submitted = st.form_submit_button("Guardar reserva", use_container_width=True)

        if submitted:
            payload = {
                "model": model,
                "color": color,
                "status": status,
                "order_date": order_date.isoformat() + "T00:00:00",
                "notes": notes or None,
            }
            try:
                r = requests.post(f"{API_BASE_URL}/api/v1/reservations", json=payload, timeout=5)
                if r.status_code == 201:
                    st.success("Reserva guardada.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Error {r.status_code}: {r.text}")
            except Exception as e:
                st.error(f"Error de conexión: {e}")
    st.stop()

# Auto-select if only one reservation; show selector in sidebar if multiple
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
