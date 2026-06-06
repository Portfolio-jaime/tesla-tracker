import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Tesla Tracker Dashboard",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# Configuration
# ============================================================================

API_BASE_URL = "http://localhost:8000"
REFRESH_INTERVAL = 30  # seconds

st.title("🚗 Tesla Tracker Dashboard")
st.markdown("Real-time tracking of your Tesla delivery")

# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    st.header("Filters")
    status_filter = st.selectbox(
        "Filter by Status",
        ["All", "RESERVED", "BOOKED", "PENDING_VIN", "IN_TRANSIT", "DELIVERED"]
    )
    model_filter = st.text_input("Filter by Model", placeholder="e.g., Model 3")
    
    if st.button("🔄 Refresh Now", use_container_width=True):
        st.rerun()


# ============================================================================
# Data Fetching
# ============================================================================

@st.cache_data(ttl=30)
def fetch_reservations(status=None, model=None):
    """Fetch reservations from API"""
    try:
        params = {"skip": 0, "limit": 100}
        if status and status != "All":
            params["status"] = status
        if model:
            params["model"] = model
        
        response = requests.get(
            f"{API_BASE_URL}/api/v1/reservations",
            params=params,
            timeout=5
        )
        response.raise_for_status()
        return response.json(), None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=30)
def fetch_stats():
    """Fetch statistics from API"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/v1/stats",
            timeout=5
        )
        response.raise_for_status()
        return response.json(), None
    except Exception as e:
        return None, str(e)


# ============================================================================
# Main Content
# ============================================================================

# Fetch data
reservations_data, res_error = fetch_reservations(
    status=None if status_filter == "All" else status_filter,
    model=model_filter if model_filter else None
)

stats_data, stats_error = fetch_stats()

if res_error:
    st.error(f"❌ Error fetching reservations: {res_error}")
    st.info("Make sure the API is running: `uvicorn app.api.main:app --reload`")
else:
    # Display Statistics
    st.subheader("📊 Overview")
    
    if stats_data:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Total Reservations",
                stats_data["total"],
                delta=None
            )
        
        with col2:
            booked = stats_data["by_status"].get("BOOKED", 0)
            st.metric(
                "Booked",
                booked,
                delta_color="inverse"
            )
        
        with col3:
            in_transit = stats_data["by_status"].get("IN_TRANSIT", 0)
            st.metric(
                "In Transit",
                in_transit,
                delta_color="off"
            )
        
        with col4:
            delivered = stats_data["by_status"].get("DELIVERED", 0)
            st.metric(
                "Delivered",
                delivered,
                delta_color="normal"
            )
    
    # Status Distribution
    st.subheader("📈 Status Distribution")
    
    if stats_data:
        col1, col2 = st.columns(2)
        
        with col1:
            status_df = pd.DataFrame(
                list(stats_data["by_status"].items()),
                columns=["Status", "Count"]
            )
            fig_status = px.pie(
                status_df,
                values="Count",
                names="Status",
                title="Reservations by Status"
            )
            st.plotly_chart(fig_status, use_container_width=True)
        
        with col2:
            model_df = pd.DataFrame(
                list(stats_data["by_model"].items()),
                columns=["Model", "Count"]
            )
            fig_model = px.bar(
                model_df,
                x="Model",
                y="Count",
                title="Reservations by Model",
                color="Count"
            )
            st.plotly_chart(fig_model, use_container_width=True)
    
    # Reservations Table
    st.subheader("📋 Reservations List")
    
    if reservations_data and len(reservations_data) > 0:
        # Convert to DataFrame
        df = pd.DataFrame(reservations_data)
        
        # Format datetime columns
        datetime_cols = ["order_date", "eta_start", "eta_end", "delivery_date", "created_at", "updated_at"]
        for col in datetime_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
        
        # Select columns to display
        display_cols = ["id", "model", "color", "status", "vin", "eta_start", "eta_end"]
        df_display = df[[col for col in display_cols if col in df.columns]]
        
        # Display table
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "model": st.column_config.TextColumn("Model"),
                "color": st.column_config.TextColumn("Color"),
                "status": st.column_config.TextColumn("Status"),
                "vin": st.column_config.TextColumn("VIN"),
                "eta_start": st.column_config.DatetimeColumn("ETA Start"),
                "eta_end": st.column_config.DatetimeColumn("ETA End"),
            }
        )
        
        st.success(f"✅ Showing {len(reservations_data)} reservations")
    else:
        st.info("No reservations found")


# ============================================================================
# Footer
# ============================================================================

st.divider()
st.markdown(
    f"<small>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small>",
    unsafe_allow_html=True
)
