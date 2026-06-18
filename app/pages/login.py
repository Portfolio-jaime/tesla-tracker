import os
import time

import requests
import streamlit as st

_API_BASE = os.environ.get("API_URL", "http://localhost:8000")


def render_login(_auth=None) -> None:
    st.markdown(
        """
        <div style='text-align:center;padding:60px 0 20px'>
            <h1>Tesla Tracker</h1>
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
                    "Conectar cuenta Tesla", use_container_width=True
                )
            if submitted:
                if not email:
                    st.error("Introduce tu email de Tesla")
                else:
                    try:
                        resp = requests.post(
                            f"{_API_BASE}/api/v1/auth/start",
                            json={"email": email},
                            timeout=10,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        st.session_state.auth_email = email
                        st.session_state.auth_state = data["state"]
                        st.session_state.auth_url = data["auth_url"]
                        st.session_state.auth_step = "waiting"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al iniciar autenticación: {e}")

        elif step == "waiting":
            st.info(
                "Haz clic en el enlace, autentícate en Tesla y esta página se actualizará automáticamente."
            )
            st.link_button(
                "Abrir autenticación Tesla",
                st.session_state.auth_url,
                use_container_width=True,
            )

            state = st.session_state.auth_state
            try:
                resp = requests.get(
                    f"{_API_BASE}/api/v1/auth/status/{state}", timeout=5
                )
                completed = resp.json().get("completed", False)
            except Exception:
                completed = False

            if completed:
                for k in ("auth_step", "auth_email", "auth_state", "auth_url"):
                    st.session_state.pop(k, None)
                st.success("¡Autenticado! Cargando dashboard...")
                st.rerun()
            else:
                with st.spinner("Esperando autenticación en Tesla..."):
                    time.sleep(2)
                st.rerun()

            if st.button("← Volver", key="auth_back"):
                for k in ("auth_step", "auth_email", "auth_state", "auth_url"):
                    st.session_state.pop(k, None)
                st.rerun()
