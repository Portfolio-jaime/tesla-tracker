from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", case_sensitive=True)

    DATABASE_URL: str = "sqlite:///./data/tesla_tracker.db"
    API_TITLE: str = "Tesla Tracker API"
    API_VERSION: str = "1.0.0"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "mixtral-8x7b-32768"
    DEBUG: bool = True
    RELOAD: bool = True
    WORKERS: int = 1


@lru_cache()
def get_settings() -> Settings:
    return Settings()
