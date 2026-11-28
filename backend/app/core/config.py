from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Adrobot"
    app_version: str = "0.1.0"

    database_url: str

    keitaro_base_url: str = (
        "https://keitaro-for-tests.etolegko.com/admin_api/v1"
    )
    keitaro_api_key: SecretStr | None = None
    keitaro_timeout: float = 15.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
