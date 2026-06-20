import os

import requests
import streamlit as st
from app.auth.tesla_auth import TeslaAuthManager

_API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def render_login(auth: TeslaAuthManager) -> None:
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
                "**Paso 1:** Haz clic en el enlace y autentícate en Tesla.  \n"
                "**Paso 2:** Después de autenticarte, copia la URL de la barra del "
                "navegador (empieza con `https://auth.tesla.com/void/callback?...`) y pégala aquí."
            )
            st.link_button(
                "Abrir autenticación Tesla",
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
                    back = st.form_submit_button("<- Volver", use_container_width=True)

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
                        with st.spinner("Sincronizando vehículos desde Tesla..."):
                            try:
                                requests.post(
                                    f"{_API_BASE}/api/v1/sync",
                                    params={"clear_all": "false"},
                                    timeout=30,
                                )
                            except Exception:
                                pass
                        st.success("¡Autenticado! Cargando dashboard...")
                        st.session_state.auth_step = "done"
                        st.rerun()
                    else:
                        st.error(
                            "Autenticación fallida. Verifica que la URL sea correcta."
                        )
