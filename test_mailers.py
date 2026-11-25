import json
import smtplib
import unittest
from email.message import EmailMessage
from unittest import mock

import mailers


def msg(to="a@x.com"):
    m = EmailMessage()
    m["To"] = to
    m["Subject"] = "hi"
    m.set_content("body")
    return m


SMTP_ENV = {"SMTP_HOST": "h", "SMTP_USER": "u@x.com", "SMTP_PASSWORD": "pw"}
GMAIL_ENV = {"GMAIL_CLIENT_ID": "id", "GMAIL_CLIENT_SECRET": "sec",
             "GMAIL_REFRESH_TOKEN": "ref"}


class FactoryTests(unittest.TestCase):
    def test_unknown_provider(self):
        with self.assertRaises(ValueError):
            mailers.create_mailer("carrier-pigeon", env={})

    def test_smtp_defaults_and_overrides(self):
        m = mailers.create_mailer("smtp", env=SMTP_ENV)
        self.assertEqual((m.host, m.port, m.security, m.sender), ("h", 465, "ssl", "u@x.com"))
        m = mailers.create_mailer(
            "smtp", env={**SMTP_ENV, "MAIL_FROM": "env@x.com"},
            smtp_host="other", smtp_security="starttls", sender="flag@x.com",
        )
        self.assertEqual((m.host, m.port, m.security, m.sender),
                         ("other", 587, "starttls", "flag@x.com"))

    def test_smtp_missing_settings(self):
        for drop in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
            env = {k: v for k, v in SMTP_ENV.items() if k != drop}
            with self.subTest(drop), self.assertRaises(ValueError):
                mailers.create_mailer("smtp", env=env)

    def test_smtp_rejects_plaintext(self):
        with self.assertRaises(ValueError):
            mailers.create_mailer("smtp", env={**SMTP_ENV, "SMTP_SECURITY": "none"})

    def test_gmail_api_missing_settings(self):
        for drop in GMAIL_ENV:
            env = {k: v for k, v in GMAIL_ENV.items() if k != drop}
            with self.subTest(drop), self.assertRaises(ValueError):
                mailers.create_mailer("gmail-api", env=env)

    def test_gmail_api_sender_optional(self):
        self.assertIsNone(mailers.create_mailer("gmail-api", env=GMAIL_ENV).sender)


class SmtpTests(unittest.TestCase):
    def test_ssl(self):
        server = mock.MagicMock()
        m = mailers.create_mailer("smtp", env=SMTP_ENV)
        with mock.patch("smtplib.SMTP_SSL", return_value=server) as f:
            self.assertEqual(mailers.send_all(m, [msg(), msg("b@x.com")]), 2)
        self.assertEqual(f.call_args[0], ("h", 465))
        server.login.assert_called_once_with("u@x.com", "pw")
        self.assertEqual(server.send_message.call_count, 2)
        server.quit.assert_called_once()

    def test_starttls(self):
        server = mock.MagicMock()
        m = mailers.create_mailer("smtp", env=SMTP_ENV, smtp_security="starttls")
        with mock.patch("smtplib.SMTP", return_value=server) as f:
            mailers.send_all(m, [msg()])
        self.assertEqual(f.call_args[0], ("h", 587))
        server.starttls.assert_called_once()
        server.login.assert_called_once()

    def test_login_failure_sends_nothing(self):
        server = mock.MagicMock()
        server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad")
        m = mailers.create_mailer("smtp", env=SMTP_ENV)
        with mock.patch("smtplib.SMTP_SSL", return_value=server), \
                self.assertRaises(mailers.MailError):
            mailers.send_all(m, [msg()])
        server.send_message.assert_not_called()
        server.quit.assert_called_once()

    def test_partial_failure_reports_who_was_sent(self):
        server = mock.MagicMock()
        server.send_message.side_effect = [None, smtplib.SMTPException("boom")]
        m = mailers.create_mailer("smtp", env=SMTP_ENV)
        with mock.patch("smtplib.SMTP_SSL", return_value=server), \
                self.assertRaises(mailers.MailError) as cm:
            mailers.send_all(m, [msg("a@x.com"), msg("b@x.com"), msg("c@x.com")])
        self.assertIn("b@x.com", str(cm.exception))
        self.assertIn("already sent to: a@x.com", str(cm.exception))


class GmailApiTests(unittest.TestCase):
    def test_flow(self):
        m = mailers.create_mailer("gmail-api", env=GMAIL_ENV)
        with mock.patch("mailers._post", return_value={"access_token": "tok"}) as post:
            mailers.send_all(m, [msg()])
        (token_call, send_call) = post.call_args_list
        url, body, _ = token_call[0]
        self.assertEqual(url, mailers.GmailApiMailer.TOKEN_URL)
        for part in (b"grant_type=refresh_token", b"refresh_token=ref", b"client_id=id"):
            self.assertIn(part, body)
        url, body, headers = send_call[0]
        self.assertEqual(url, mailers.GmailApiMailer.SEND_URL)
        self.assertEqual(headers["Authorization"], "Bearer tok")
        import base64
        raw = base64.urlsafe_b64decode(json.loads(body)["raw"])
        self.assertIn(b"To: a@x.com", raw)

    def test_no_access_token(self):
        m = mailers.create_mailer("gmail-api", env=GMAIL_ENV)
        with mock.patch("mailers._post", return_value={}), \
                self.assertRaises(mailers.MailError):
            mailers.send_all(m, [msg()])

    def test_http_error_becomes_mail_error_without_leaking_secrets(self):
        import io, urllib.error
        err = urllib.error.HTTPError("https://x", 401, "no", {}, io.BytesIO(b"invalid_grant"))
        with mock.patch("urllib.request.urlopen", side_effect=err), \
                self.assertRaises(mailers.MailError) as cm:
            mailers._post("https://oauth2.googleapis.com/token?x=secret", b"", {})
        self.assertIn("401", str(cm.exception))
        self.assertNotIn("secret", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
