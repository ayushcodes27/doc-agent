import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # LLM Config
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    
    # Database & Cache
    DATABASE_URL: str = "postgresql://docagent:docagent@localhost:5432/docagent"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # App Settings
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    MAX_FILE_SIZE_MB: int = 10
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
