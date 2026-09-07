import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # LLM Config
    LLM_PROVIDER: str = "auto"  # 'auto', 'gemini', 'github_models', 'groq'
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GITHUB_TOKEN: str = ""
    GITHUB_MODEL: str = "gpt-4o-mini"
    GITHUB_ENDPOINT: str = "https://models.inference.ai.azure.com"
    GROQ_API_KEY: str = ""
    
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
