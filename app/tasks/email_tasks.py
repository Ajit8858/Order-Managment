import logging
import smtplib
from email.mime.text import MIMEText

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.EMAIL_FROM, [to_email], msg.as_string())


@celery_app.task(name="app.tasks.email_tasks.send_order_confirmation_email", bind=True, max_retries=3)
def send_order_confirmation_email(self, to_email: str, order_id: str, total_amount: str):
    subject = f"Order Confirmation - #{order_id[:8]}"
    body = (
        f"Thanks for your order!\n\n"
        f"Order ID: {order_id}\n"
        f"Total: {total_amount}\n\n"
        f"We'll notify you again once it ships."
    )
    if not settings.EMAIL_ENABLED:
        logger.info("[SIMULATED EMAIL] to=%s subject=%s body=%s", to_email, subject, body)
        return {"sent": False, "simulated": True}

    try:
        _send_smtp(to_email, subject, body)
        return {"sent": True}
    except Exception as exc:
        logger.exception("Failed to send order confirmation email")
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="app.tasks.email_tasks.send_payment_failed_email", bind=True, max_retries=3)
def send_payment_failed_email(self, to_email: str, order_id: str, reason: str):
    subject = f"Payment Failed - Order #{order_id[:8]}"
    body = f"Your payment for order {order_id} failed.\nReason: {reason}\nPlease retry from your order history."
    if not settings.EMAIL_ENABLED:
        logger.info("[SIMULATED EMAIL] to=%s subject=%s body=%s", to_email, subject, body)
        return {"sent": False, "simulated": True}
    try:
        _send_smtp(to_email, subject, body)
        return {"sent": True}
    except Exception as exc:
        logger.exception("Failed to send payment-failed email")
        raise self.retry(exc=exc, countdown=30)
