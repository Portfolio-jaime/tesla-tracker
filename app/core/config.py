from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Configuración de la aplicación"""
    
    # Database
    DATABASE_URL: str = "sqlite:///./data/tesla_tracker.db"
    
    # API
    API_TITLE: str = "Tesla Tracker API"
    API_VERSION: str = "1.0.0"
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    
    # Groq AI
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "mixtral-8x7b-32768"
    
    # App Settings
    DEBUG: bool = True
    RELOAD: bool = True
    WORKERS: int = 1
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get settings instance (cached)"""
    return Settings()
