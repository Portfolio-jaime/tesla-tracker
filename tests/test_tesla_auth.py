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
