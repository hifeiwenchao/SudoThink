"""SMTP boundary tests without sending real mail or reading application secrets."""
import importlib
import importlib.util
import os
import smtplib
import ssl
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def config(**overrides):
    values = dict(
        SMTP_HOST="smtp.exmail.qq.com", SMTP_PORT=465, SMTP_SECURITY="ssl",
        SMTP_USERNAME="sender@example.com", SMTP_PASSWORD="secret-not-for-errors",
        SMTP_FROM_EMAIL="", SMTP_FROM_NAME="SudoThink 提醒",
        SMTP_TIMEOUT_SECONDS=15,
    )
    return SimpleNamespace(**(values | overrides))


class Transport:
    def __init__(self, events, messages, failure=None):
        self.events, self.messages, self.failure = events, messages, failure

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.events.append("closed")

    def ehlo(self):
        self.events.append("ehlo")

    def starttls(self, *, context):
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        self.events.append("starttls")

    def login(self, username, password):
        self.events.append(("login", username, password))
        if self.failure:
            raise self.failure

    def send_message(self, message):
        self.messages.append(message)
        self.events.append("sent")
        return {}


class MailTests(unittest.TestCase):
    def mail(self):
        self.assertIsNotNone(importlib.util.find_spec("app.core.mail"), "SMTP sender is missing")
        return importlib.import_module("app.core.mail")

    def test_ssl_mail_contains_utf8_body_and_only_configured_recipient(self):
        mail = self.mail()
        events, messages, connections = [], [], []

        def connect(host, port, *, timeout, context):
            self.assertEqual((host, port, timeout), ("smtp.exmail.qq.com", 465, 15))
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            connections.append(host)
            return Transport(events, messages)

        with patch.object(smtplib, "SMTP_SSL", side_effect=connect):
            mail.send_mail("待办提醒：续费", "请于今天完成续费。", "admin@example.com", config=config())
        self.assertEqual(len(connections), 1)
        self.assertEqual(events[-2:], ["sent", "closed"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]["Subject"]), "待办提醒：续费")
        self.assertEqual(messages[0]["From"].addresses[0].addr_spec, "sender@example.com")
        self.assertEqual(messages[0]["To"].addresses[0].addr_spec, "admin@example.com")
        self.assertEqual(messages[0].get_content().strip(), "请于今天完成续费。")

    def test_starttls_is_completed_before_authentication(self):
        mail = self.mail()
        events, messages = [], []
        with patch.object(smtplib, "SMTP", return_value=Transport(events, messages)):
            mail.send_mail("提醒", "内容", "admin@example.com", config=config(
                SMTP_PORT=587, SMTP_SECURITY="starttls",
            ))
        self.assertEqual(events[:3], ["ehlo", "starttls", "ehlo"])
        self.assertEqual(events[3][0], "login")
        self.assertEqual(len(messages), 1)

    def test_authentication_error_is_actionable_without_leaking_response_or_password(self):
        mail = self.mail()
        failure = smtplib.SMTPAuthenticationError(535, b"secret-not-for-errors upstream details")
        with patch.object(smtplib, "SMTP_SSL", return_value=Transport([], [], failure)):
            with self.assertRaises(mail.MailDeliveryError) as caught:
                mail.send_mail("提醒", "内容", "admin@example.com", config=config())
        self.assertIn("认证", str(caught.exception))
        self.assertNotIn("secret-not-for-errors", str(caught.exception))

    def test_missing_insecure_and_malformed_settings_are_not_ready(self):
        mail = self.mail()
        self.assertTrue(mail.smtp_ready(config()))
        for changes in (
            {"SMTP_PASSWORD": ""}, {"SMTP_HOST": ""}, {"SMTP_PORT": 0},
            {"SMTP_SECURITY": "none"}, {"SMTP_FROM_EMAIL": "not-an-email"},
            {"SMTP_FROM_NAME": "name\r\nBcc: injected@example.com"},
            {"SMTP_TIMEOUT_SECONDS": 0},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(mail.smtp_ready(config(**changes)))

    def test_explicit_recipient_is_validated_without_any_environment_fallback(self):
        mail = self.mail()
        self.assertEqual(mail.validate_recipient("  notify@EXAMPLE.com  "), "notify@example.com")
        for address in ("", "bad-address", "a@example.com,b@example.com", "A <a@example.com>", "a@example.com\r\n"):
            with self.subTest(address=address), self.assertRaises(mail.MailDeliveryError):
                mail.validate_recipient(address)

    def test_mail_rejects_header_injection_before_opening_connection(self):
        mail = self.mail()
        with patch.object(smtplib, "SMTP_SSL", side_effect=AssertionError("must not connect")):
            for subject, recipient in (
                ("bad\nBcc: other@example.com", "admin@example.com"),
                ("提醒", "admin@example.com\r\nBcc: other@example.com"),
            ):
                with self.subTest(subject=subject), self.assertRaises(mail.MailDeliveryError):
                    mail.send_mail(subject, "内容", recipient, config=config())


if __name__ == "__main__":
    unittest.main()
