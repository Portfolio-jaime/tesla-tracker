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
