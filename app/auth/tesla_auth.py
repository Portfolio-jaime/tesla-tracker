import json
import os
from typing import Optional, Tuple

import teslapy

VOID_CALLBACK = "https://auth.tesla.com/void/callback"


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

    def start_auth(self, email: str, redirect_uri: Optional[str] = None) -> Tuple[str, str, str]:
        """Start OAuth2 PKCE flow. Returns (auth_url, state, code_verifier)."""
        os.makedirs(os.path.dirname(os.path.abspath(self._token_path)), exist_ok=True)
        tesla = teslapy.Tesla(email, cache_file=self._token_path)
        tesla.scope = ('openid', 'email', 'offline_access', 'vehicle_device_data', 'vehicle_location', 'vehicle_cmds', 'vehicle_charging_cmds')
        state = tesla.new_state()
        code_verifier = tesla.new_code_verifier()
        kwargs: dict = {
            "state": state,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri or VOID_CALLBACK,
        }
        auth_url = tesla.authorization_url(**kwargs)
        return auth_url, state, code_verifier

    def complete_auth(
        self, email: str, callback_url: str, state: str, code_verifier: str,
        redirect_uri: Optional[str] = None,
    ) -> bool:
        """Complete OAuth2 PKCE flow. Returns True on success."""
        tesla = teslapy.Tesla(email, cache_file=self._token_path)
        kwargs: dict = {
            "authorization_response": callback_url,
            "state": state,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri or VOID_CALLBACK,
        }
        try:
            tesla.fetch_token(**kwargs)
        except Exception:
            return False
        return bool(tesla.authorized)

    def get_tesla_client(self) -> teslapy.Tesla:
        email = self._get_cached_email()
        if not email:
            raise RuntimeError("No hay sesión activa — tokens no encontrados")
        return teslapy.Tesla(email, cache_file=self._token_path)

    def get_vehicles(self) -> list:
        """Return list of vehicles from Tesla API."""
        return self.get_tesla_client().vehicle_list()

    def get_cached_email(self) -> Optional[str]:
        """Return the email stored in the token cache, or None."""
        if not os.path.exists(self._token_path):
            return None
        try:
            with open(self._token_path) as f:
                cache = json.load(f)
            if cache:
                return next(iter(cache))
        except (json.JSONDecodeError, OSError):
            self.logout()  # remove corrupted file
        return None

    def logout(self) -> None:
        if os.path.exists(self._token_path):
            os.remove(self._token_path)

    def _get_cached_email(self) -> Optional[str]:
        return self.get_cached_email()
