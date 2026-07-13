import logging
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import render_template

logger = logging.getLogger(__name__)


def _get_config():
    return {
        "server": os.getenv("MAIL_SERVER", "smtp.gmail.com"),
        "port": int(os.getenv("MAIL_PORT", "587")),
        "use_tls": os.getenv("MAIL_USE_TLS", "true").lower() == "true",
        "username": os.getenv("MAIL_USERNAME", ""),
        "password": os.getenv("MAIL_PASSWORD", ""),
        "default_sender": os.getenv("MAIL_DEFAULT_SENDER", "noreply@tradingplatform.com"),
    }


def send_email(to_email, subject, html_body, text_body=None):
    cfg = _get_config()
    if not cfg["username"] or not cfg["password"]:
        logger.warning("Email not sent: MAIL_USERNAME or MAIL_PASSWORD not configured")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["default_sender"]
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if cfg["use_tls"]:
            context = ssl.create_default_context()
            with smtplib.SMTP(cfg["server"], cfg["port"]) as server:
                server.starttls(context=context)
                server.login(cfg["username"], cfg["password"])
                server.sendmail(cfg["default_sender"], to_email, msg.as_string())
        else:
            with smtplib.SMTP(cfg["server"], cfg["port"]) as server:
                server.login(cfg["username"], cfg["password"])
                server.sendmail(cfg["default_sender"], to_email, msg.as_string())
        logger.info("Email sent to %s: %s", to_email, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False


def send_welcome_email(user):
    html = render_template("emails/welcome.html", user=user)
    return send_email(user.email, "Welcome to Trading Platform", html)


def send_password_reset_email(user, reset_url):
    html = render_template("emails/reset_password.html", user=user, reset_url=reset_url)
    return send_email(user.email, "Reset your Trading Platform password", html)


def send_member_added_email(user, org_name, added_by_name):
    html = render_template("emails/member_added.html", user=user, org_name=org_name, added_by_name=added_by_name)
    return send_email(user.email, f"You've been added to {org_name}", html)
