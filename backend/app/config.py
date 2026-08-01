from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    field_encryption_key: str
    tbank_base_url: str = "https://business.tbank.ru/openapi"
    env: str = "development"

    class Config:
        env_file = ".env"


settings = Settings()
