from pydantic import AnyHttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    airflow_health_url: AnyHttpUrl
    internal_proxy_token: SecretStr

    model_config = SettingsConfigDict(case_sensitive=False, env_file=None)

    @field_validator("internal_proxy_token")
    @classmethod
    def reject_empty_proxy_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("internal proxy token must not be empty")
        return value
