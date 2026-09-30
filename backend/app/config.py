

# This is a configuration file for the backend application. It uses Pydantic's BaseSettings to manage application settings and configurations. The SettingsConfigDict is used to define the structure and validation of the settings.
from pydantic_settings import BaseSettings, SettingsConfigDict 

class Settings(BaseSettings):
    """Runtime configuration for the Morning Manna API."""

    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "Morning Manna API"
    environment: str = "local"


settings = Settings()