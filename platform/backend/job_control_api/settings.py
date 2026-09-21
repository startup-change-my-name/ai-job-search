from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    airflow_health_url: AnyHttpUrl
    internal_proxy_token: SecretStr

    model_config = SettingsConfigDict(case_sensitive=False, env_file=None)
