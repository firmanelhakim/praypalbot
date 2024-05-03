import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os

from credentials import SENDER_EMAIL, SENDER_PASSWORD, RECIPIENTS


def send_email(subject, message, file_path=None):
    """
    Sends an email using Gmail's SMTP server with secure connection (TLS) and an optional attachment.

    Args:
        subject (str): The subject line of the email.
        message (str): The body of the email message.
        file_path (str, optional): The path to the file you want to attach. Defaults to None.

    Returns:
        bool: True if the email is sent successfully, False otherwise.
    """

    try:
        # Use Gmail's SMTP server with TLS encryption
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()

        # Login with sender credentials (consider using app passwords)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)

        # Create a multipart message for text and attachment (if provided)
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECIPIENTS
        msg["Subject"] = subject

        # Attach the text message
        text_part = MIMEText(message, "plain")
        msg.attach(text_part)

        # Attach the file (if a valid path is provided)
        if file_path and os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                file_part = MIMEApplication(f.read(), "octet-stream")
                file_part.add_header(
                    "Content-Disposition",
                    'attachment; filename="%s"' % os.path.basename(file_path),
                )
                msg.attach(file_part)

        # Send the email
        server.sendmail(SENDER_EMAIL, RECIPIENTS, msg.as_string())

        # Close the connection
        server.quit()

        return True

    except Exception as e:
        print(f"Error sending email: {e}")
        return False
