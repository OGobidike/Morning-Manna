

"""Configuration for the backend, read from environment variables or a .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Morning Manna API."""

    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "Morning Manna API"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://manna:manna@localhost:5432/manna"


settings = Settings()
