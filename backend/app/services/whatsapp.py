"""Consent-aware Meta WhatsApp Cloud API delivery."""
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests

from app.core.config import settings


def _logger() -> logging.Logger:
    logger = logging.getLogger("edvatiq.whatsapp")
    log_path = Path(__file__).resolve().parents[2] / "logs" / "whatsapp.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not any(isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path for handler in logger.handlers):
        handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        digits = f"{settings.WHATSAPP_DEFAULT_COUNTRY_CODE}{digits}"
    if not 8 <= len(digits) <= 15:
        raise ValueError("Phone number must include a valid country code")
    return digits


def _masked_phone(value: str) -> str:
    try:
        digits = normalize_phone(value)
    except ValueError:
        return "invalid-phone"
    return f"{digits[:2]}{'*' * max(len(digits) - 6, 2)}{digits[-4:]}"


def send_whatsapp_message(
    recipient: str,
    *,
    body: str | None = None,
    template_name: str | None = None,
    template_language: str | None = None,
    template_variables: list[str] | None = None,
) -> str | None:
    logger = _logger()
    masked = _masked_phone(recipient)
    missing = [name for name, value in {
        "WHATSAPP_TOKEN": settings.WHATSAPP_TOKEN,
        "WHATSAPP_PHONE_NUMBER_ID": settings.WHATSAPP_PHONE_NUMBER_ID,
    }.items() if not value]
    if missing:
        logger.warning("whatsapp_skipped recipient=%s missing=%s", masked, ",".join(missing))
        return None
    try:
        destination = normalize_phone(recipient)
    except ValueError:
        logger.error("whatsapp_invalid_recipient recipient=%s", masked)
        return None

    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": destination}
    if template_name:
        parameters = [{"type": "text", "text": str(value)[:1024]} for value in (template_variables or [])]
        payload.update({
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": template_language or settings.WHATSAPP_TEMPLATE_LANGUAGE},
                **({"components": [{"type": "body", "parameters": parameters}]} if parameters else {}),
            },
        })
        message_type = f"template:{template_name}"
    elif body:
        payload.update({"type": "text", "text": {"preview_url": False, "body": body[:4096]}})
        message_type = "text"
    else:
        raise ValueError("WhatsApp message requires a template or body")

    logger.info("whatsapp_send_started recipient=%s message_type=%s", masked, message_type)
    try:
        response = requests.post(
            f"https://graph.facebook.com/{settings.WHATSAPP_GRAPH_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        data = response.json() if response.content else {}
        if not response.ok:
            error = data.get("error", {})
            logger.error(
                "whatsapp_send_failed recipient=%s http_status=%s provider_code=%s provider_type=%s",
                masked, response.status_code, error.get("code", "unknown"), error.get("type", "unknown"),
            )
            return None
        message_id = (data.get("messages") or [{}])[0].get("id")
        if not message_id:
            logger.error("whatsapp_response_invalid recipient=%s", masked)
            return None
    except requests.RequestException as exc:
        logger.error("whatsapp_send_failed recipient=%s error_type=%s", masked, type(exc).__name__)
        return None
    logger.info("whatsapp_sent recipient=%s message_id=%s", masked, message_id)
    return message_id
