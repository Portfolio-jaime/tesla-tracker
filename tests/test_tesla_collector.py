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
