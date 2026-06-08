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
# Main data
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
# Vehicle detail
# ============================================================================

if reservations_data:
    options = {
        f"{r['model']} — VIN: {(r.get('vin') or 'Sin VIN')[:10]} [{r['status']}]": r
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
# Distribution + table
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
