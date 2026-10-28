

"""Configuration for the backend, read from environment variables or a .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Morning Manna API."""

    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "Morning Manna API"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://manna:manna@localhost:5432/manna"

    # The data lake (S3-compatible). Left empty, the API doesn't write to a lake at all.
    lake_url: str = ""
    lake_bucket: str = "morning-manna-lake"
    lake_access_key: str = "lake"
    lake_secret_key: str = "lake-secret"

settings = Settings()
