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


def test_patches_sso_client_id_when_configured(monkeypatch):
    """TeslaAuthManager must patch teslapy.SSO_CLIENT_ID if TESLA_CLIENT_ID is set."""
    import teslapy
    # setattr registers original value with pytest — guaranteed restore even if test fails
    monkeypatch.setattr(teslapy, "SSO_CLIENT_ID", teslapy.SSO_CLIENT_ID)
    monkeypatch.setenv("TESLA_CLIENT_ID", "my-fleet-client-id")
    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.auth.tesla_auth import TeslaAuthManager
    TeslaAuthManager()  # __init__ must patch the global

    assert teslapy.SSO_CLIENT_ID == "my-fleet-client-id"
    get_settings.cache_clear()  # clean settings cache for subsequent tests
