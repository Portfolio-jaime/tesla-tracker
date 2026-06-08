import logging
import requests

logger = logging.getLogger(__name__)


class TelegramAlert:
    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._configured = bool(token and chat_id)

    def send(self, model: str, vin: str, old_status: str, new_status: str) -> bool:
        message = (
            f"🚗 *{model}*\n"
            f"VIN: `{vin or 'Sin VIN'}`\n"
            f"Estado: {old_status} → *{new_status}*"
        )
        if new_status == "DELIVERED":
            message += "\n✅ ¡Entrega confirmada!"
        elif new_status == "IN_TRANSIT":
            message += "\n🚛 En camino a tu centro de entrega"

        if not self._configured:
            logger.info(
                f"[TelegramAlert] Sin configurar — alerta local: "
                f"{model} ({vin}): {old_status} → {new_status}"
            )
            return False

        try:
            url = self.BASE_URL.format(token=self.token)
            response = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=5,
            )
            response.raise_for_status()
            logger.info(f"Alerta Telegram enviada: {model} ({vin}) → {new_status}")
            return True
        except Exception as e:
            logger.error(f"Error enviando alerta Telegram: {e}")
            return False
