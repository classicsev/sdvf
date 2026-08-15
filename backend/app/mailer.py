import logging
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid, formatdate

from app.config import settings

logger = logging.getLogger(__name__)


def _send(to_email: str, subject: str, body: str) -> bool:
    """Отправляет письмо через self-hosted Postfix (settings.smtp_host).
    Возвращает False при любой ошибке вместо исключения — сбой почты не должен
    ронять регистрацию/API-запрос, инициировавший отправку."""
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to_email
    msg["Subject"] = subject
    # Без этих двух заголовков Gmail отклоняет письмо на этапе DATA (RFC 5322
    # требует Message-ID; проверено вживую — реальный bounce от Gmail с
    # причиной "Messages missing a valid Message-ID header are not accepted").
    # smtplib/EmailMessage их сами не проставляют — только явно.
    msg["Message-ID"] = make_msgid(domain=settings.mail_from.split("@")[-1])
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Не удалось отправить письмо на %s: %s", to_email, exc)
        return False


def send_sso_link_confirmation_email(to_email: str, token: str, client_name: str) -> bool:
    # Ссылка ведёт сразу на бэкенд (не на фронтенд-SPA) — конечное действие тут
    # просто редирект с кодом на колбэк СДВФ, промежуточный экран не нужен.
    link = f"{settings.backend_base_url}/oauth/link-confirm?token={token}"
    body = (
        "Здравствуйте!\n\n"
        f"Кто-то запросил привязку вашего аккаунта «Учёт Движения» к аккаунту {client_name}.\n"
        "Если это вы — подтвердите привязку, перейдя по ссылке:\n"
        f"{link}\n\n"
        "Ссылка действует 30 минут. Если вы не запрашивали привязку — просто "
        "проигнорируйте это письмо, аккаунты не будут связаны."
    )
    return _send(to_email, f"Подтверждение привязки аккаунта — {client_name}", body)


def send_verification_email(to_email: str, token: str) -> bool:
    link = f"{settings.frontend_base_url}/verify-email?token={token}"
    body = (
        "Здравствуйте!\n\n"
        "Подтвердите email для аккаунта в «Учёт Движения», перейдя по ссылке:\n"
        f"{link}\n\n"
        "Ссылка действует 24 часа. Если вы не регистрировались — просто "
        "проигнорируйте это письмо.\n\n"
        "Если письмо попало в папку «Спам» — это ожидаемо для нового отправителя, "
        "пометьте его как «Не спам», чтобы следующие письма приходили нормально."
    )
    return _send(to_email, "Подтверждение email — Учёт Движения", body)
