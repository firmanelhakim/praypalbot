import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from credentials import SENDER_EMAIL, SENDER_PASSWORD, RECIPIENTS

logger = logging.getLogger(__name__)


def send_email(subject, message, file_path=None):
    """Sends an alert email over Gmail SMTP with TLS.

    Args:
        subject (str): Subject line.
        message (str): Body text.
        file_path (str, optional): File to attach.

    Returns:
        bool: True if sent, False otherwise.
    """
    # Alerting is optional — a missing mail config must never take the bot down.
    if not (SENDER_EMAIL and SENDER_PASSWORD and RECIPIENTS):
        logger.warning(
            "Email not configured (SENDER_EMAIL/SENDER_PASSWORD/RECIPIENTS); "
            "skipping alert: %s",
            subject,
        )
        return False

    recipients = [addr.strip() for addr in RECIPIENTS.split(",") if addr.strip()]

    server = None
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)

        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        if file_path and os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                file_part = MIMEApplication(f.read(), "octet-stream")
                file_part.add_header(
                    "Content-Disposition",
                    'attachment; filename="%s"' % os.path.basename(file_path),
                )
                msg.attach(file_part)

        server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
        return True

    except Exception:
        logger.error("Error sending email alert %r", subject, exc_info=True)
        return False

    finally:
        # quit() here so a failure mid-send can't leak the socket.
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass
