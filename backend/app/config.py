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

    # Почта (self-hosted через Postfix на проде) — используется для писем
    # подтверждения email. В dev SMTP_HOST не поднят — отправка просто не
    # удастся и будет проглочена (см. app/mailer.py), остальной флоу это не ломает.
    smtp_host: str = "localhost"
    smtp_port: int = 25
    mail_from: str = "noreply@localhost"
    # Базовый URL фронтенда — нужен, чтобы собрать ссылку в письме подтверждения
    # и адрес, куда бэкенд редиректит после OAuth-колбэка.
    frontend_base_url: str = "http://localhost:3000"
    # Публичный URL самого бэкенда — redirect_uri в OAuth должен указывать на
    # бэкенд (он обменивает code на токен), а не на фронтенд. В проде это
    # отдельный поддомен (см. Caddyfile: api.uvost.ru), не совпадает с frontend_base_url.
    backend_base_url: str = "http://localhost:8000"

    # OAuth — пусто по умолчанию: если для провайдера не заданы client_id/secret,
    # соответствующая кнопка на фронте не показывается (см. GET /auth/oauth/providers).
    vk_client_id: str = ""
    vk_client_secret: str = ""
    yandex_client_id: str = ""
    yandex_client_secret: str = ""
    sber_client_id: str = ""
    sber_client_secret: str = ""

    # Интеграция с СДВФ (sdvf.ru) — генерация Счёт/УПД из карточки заказа.
    # Пусто по умолчанию — кнопки генерации на фронте не показываются, пока не настроено.
    sdvf_base_url: str = ""
    sdvf_api_key: str = ""

    # Единый вход: Учёт выступает identity-провайдером для СДВФ (routers/identity_provider.py).
    # redirect_uri — жёсткий allowlist ровно одного доверенного клиента (не
    # произвольный параметр запроса) — защита от open redirect. Пусто = выключено.
    sdvf_sso_redirect_uri: str = ""
    sdvf_sso_client_secret: str = ""
    # Отдельный колбэк для привязки аккаунтов (в отличие от входа) — см.
    # identity_provider.py. Тот же client_secret и тот же /oauth/token, разный
    # redirect_uri и разная логика на приёмной стороне (СДВФ).
    sdvf_sso_link_redirect_uri: str = ""

    # Обратное направление: Учёт потребляет identity от СДВФ (routers/sdvf_login.py,
    # зеркало identity_provider.py) — кнопка "Войти через СДВФ" на экране входа.
    # sdvf_base_url общий (выше), секрет свой — отдельный от sdvf_sso_client_secret,
    # который используется для входящего направления SDVF→Учёт. Пусто = кнопка
    # на фронте не показывается.
    sdvf_client_secret: str = ""

    # DaData — автозаполнение реквизитов по ИНН (ЕГРЮЛ/ЕГРИП), тот же ключ, что
    # и в СДВФ. Только через бэкенд-прокси (routers/dadata.py): ключ на фронт не
    # отдаём, иначе его вычитают из исходников страницы и потратят наш лимит.
    dadata_api_key: str = ""

    class Config:
        env_file = ".env"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
