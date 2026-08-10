"""Transactional email delivery through Resend with optional SMTP fallback."""
import logging
import smtplib
from email.message import EmailMessage
from logging.handlers import RotatingFileHandler
from pathlib import Path

import resend
from resend.exceptions import ResendError

from app.core.config import settings
from app.services.email_templates import render_auth_email


def _email_logger() -> logging.Logger:
    logger = logging.getLogger("edvatiq.email")
    log_path = Path(__file__).resolve().parents[2] / "logs" / "email.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not any(isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path for handler in logger.handlers):
        handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def _masked_email(value: str) -> str:
    address = value.rsplit("<", 1)[-1].rstrip("> ").strip()
    local, separator, domain = address.partition("@")
    if not separator:
        return "invalid-address"
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(2, len(local) - len(visible))}@{domain}"


def send_email(recipient: str, subject: str, text: str, html: str, purpose: str = "transactional") -> str | None:
    provider = settings.EMAIL_PROVIDER
    if provider == "resend":
        return _send_with_resend(recipient, subject, text, html, purpose)
    if provider == "smtp":
        return _send_with_smtp(recipient, subject, text, html, purpose)
    _email_logger().error("mail_provider_invalid provider=%s purpose=%s", provider, purpose)
    return None


def _send_with_resend(recipient: str, subject: str, text: str, html: str, purpose: str) -> str | None:
    logger = _email_logger()
    masked_recipient = _masked_email(recipient)
    missing = [name for name, value in {
        "RESEND_API_KEY": settings.RESEND_API_KEY,
        "RESEND_FROM_EMAIL": settings.RESEND_FROM_EMAIL,
    }.items() if not value]
    if missing:
        logger.warning("mail_skipped provider=resend purpose=%s recipient=%s missing=%s", purpose, masked_recipient, ",".join(missing))
        return None

    sender_mode = "test_only" if settings.RESEND_FROM_EMAIL.lower().endswith("@resend.dev>") or settings.RESEND_FROM_EMAIL.lower().endswith("@resend.dev") else "verified_domain"
    logger.info("resend_send_started purpose=%s recipient=%s sender=%s sender_mode=%s", purpose, masked_recipient, _masked_email(settings.RESEND_FROM_EMAIL), sender_mode)
    try:
        resend.api_key = settings.RESEND_API_KEY
        response = resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [recipient],
            "subject": subject,
            "text": text,
            "html": html,
        })
        message_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        if not message_id:
            logger.error("resend_response_invalid purpose=%s recipient=%s", purpose, masked_recipient)
            return None
    except ResendError as exc:
        message = (exc.message or "").lower()
        if "only send testing emails to your own email" in message:
            reason = "test_sender_recipient_restricted"
        elif "domain" in message and "not verified" in message:
            reason = "sender_domain_not_verified"
        elif exc.error_type == "invalid_api_key":
            reason = "invalid_api_key"
        else:
            reason = exc.error_type or "provider_rejected"
        logger.error(
            "resend_send_failed purpose=%s recipient=%s reason=%s status_code=%s",
            purpose, masked_recipient, reason, exc.code,
        )
        return None
    except Exception as exc:
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        logger.error(
            "resend_send_failed purpose=%s recipient=%s error_type=%s status_code=%s",
            purpose, masked_recipient, type(exc).__name__, status_code or "unknown",
        )
        return None
    logger.info("resend_sent purpose=%s recipient=%s message_id=%s", purpose, masked_recipient, message_id)
    return str(message_id)


def _send_with_smtp(recipient: str, subject: str, text: str, html: str, purpose: str) -> str | None:
    logger = _email_logger()
    masked_recipient = _masked_email(recipient)
    missing = [name for name, value in {
        "SMTP_HOST": settings.SMTP_HOST,
        "SMTP_USERNAME": settings.SMTP_USERNAME,
        "SMTP_PASSWORD": settings.SMTP_PASSWORD,
    }.items() if not value]
    if missing:
        logger.warning("mail_skipped provider=smtp purpose=%s recipient=%s missing=%s", purpose, masked_recipient, ",".join(missing))
        return None

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME}>"
    message["To"] = recipient
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    logger.info(
        "smtp_send_started purpose=%s recipient=%s host=%s port=%s tls=%s username=%s",
        purpose, masked_recipient, settings.SMTP_HOST, settings.SMTP_PORT,
        settings.SMTP_USE_TLS, _masked_email(settings.SMTP_USERNAME),
    )
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            if settings.SMTP_USE_TLS:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            refused = smtp.send_message(message)
        if refused:
            logger.error("smtp_recipient_refused purpose=%s recipient=%s refused_count=%s", purpose, masked_recipient, len(refused))
            return None
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("smtp_authentication_failed host=%s username=%s smtp_code=%s", settings.SMTP_HOST, _masked_email(settings.SMTP_USERNAME), exc.smtp_code)
        return None
    except smtplib.SMTPRecipientsRefused:
        logger.error("smtp_recipient_refused purpose=%s recipient=%s", purpose, masked_recipient)
        return None
    except smtplib.SMTPDataError as exc:
        detail = (exc.smtp_error or b"").decode("utf-8", errors="ignore").lower() if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error).lower()
        reason = "daily_limit_exceeded" if "daily user sending limit exceeded" in detail else "provider_rejected"
        logger.error("smtp_provider_rejected purpose=%s recipient=%s reason=%s smtp_code=%s", purpose, masked_recipient, reason, exc.smtp_code)
        return None
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("smtp_send_failed purpose=%s recipient=%s error_type=%s", purpose, masked_recipient, type(exc).__name__)
        return None
    logger.info("smtp_sent purpose=%s recipient=%s", purpose, masked_recipient)
    return "smtp-accepted"


def send_auth_code_email(recipient: str, code: str, purpose: str, first_name: str = "") -> bool:
    expires_minutes = settings.PASSWORD_RESET_TTL_MINUTES if purpose == "password_reset" else settings.AUTH_CODE_TTL_MINUTES
    subject, text, html = render_auth_email(
        code=code, purpose=purpose, first_name=first_name,
        app_url=settings.APP_URL, expires_minutes=expires_minutes,
    )
    return bool(send_email(recipient, subject, text, html, purpose))
