import json
import os
import requests as _requests

from app.auth.tesla_auth import TeslaAuthManager

# Fleet API only serves delivered/active vehicles; pre-delivery orders are not exposed.
# Tokens issued for Fleet API client_id are rejected by owner-api.teslamotors.com.
_FLEET_REGIONS = [
    "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "https://fleet-api.prd.eu.vn.cloud.tesla.com",
]


class TeslaCollector:
    STATUS_MAP = {
        "new": "CONFIRMED",
        "factory": "MANUFACTURING",
        "transit": "IN_TRANSIT",
        "delivered": "DELIVERED",
        "online": "DELIVERED",
        "asleep": "DELIVERED",
        "offline": "DELIVERED",
    }
    MODEL_MAP = {
        "model3": "Model 3",
        "modely": "Model Y",
        "modelx": "Model X",
        "models": "Model S",
        "modelq": "Model Q",
        "cybertruck": "Cybertruck",
    }

    def __init__(self, auth: TeslaAuthManager):
        self._auth = auth
        self._token = self._extract_token()

    def _extract_token(self) -> str:
        token_path = self._auth._token_path
        with open(token_path) as f:
            cache = json.load(f)
        email = next(iter(cache))
        return cache[email]["sso"]["access_token"]

    def _fleet_get(self, path: str) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"}
        for base in _FLEET_REGIONS:
            r = _requests.get(f"{base}{path}", headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 403):
                break  # token issue, no point trying other regions
        return {"response": [], "count": 0}

    def fetch_reservations(self) -> list:
        data = self._fleet_get("/api/1/vehicles")
        vehicles = data.get("response") or []
        return [self._map_vehicle(v) for v in vehicles]

    def _map_vehicle(self, v: dict) -> dict:
        cfg = v.get("vehicle_config") or {}
        car_type = cfg.get("car_type", "")
        return {
            "vin": v.get("vin"),
            "model": self.MODEL_MAP.get(car_type.lower(), car_type or "Desconocido"),
            "color": cfg.get("exterior_color") or v.get("color") or "",
            "status": self.STATUS_MAP.get(v.get("state", ""), "DELIVERED"),
            "notes": v.get("display_name") or "",
        }
