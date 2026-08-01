from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    field_encryption_key: str
    tbank_base_url: str = "https://business.tbank.ru/openapi"
    # Список разрешённых origin'ов фронтенда через запятую (без пробелов).
    # В проде указать реальный домен(ы), напр. "https://finance.example.ru".
    cors_origins: str = "http://localhost:3000"
    env: str = "development"

    class Config:
        env_file = ".env"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
