from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    square_token: str
    square_environment: str = "SANDBOX"
    square_api_version: str = "2026-05-20"
    square_webhook_signature_key: str = ""
    square_webhook_url: str = ""


settings = Settings()
