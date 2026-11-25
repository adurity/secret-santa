"""Mail providers for secret_santa.py.

Each provider is a context manager with a ``send(EmailMessage)`` method and a
``sender`` attribute (the From address, possibly None).  Entering the context
connects/authenticates, so credential problems surface before anything is
sent.  Secrets come from the environment only, never from CLI arguments.

To add a provider: subclass ``Mailer``, then register a factory in
``PROVIDERS``.
"""

import base64
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request


class MailError(Exception):
    pass


class Mailer:
    sender = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send(self, msg):
        raise NotImplementedError


class SmtpMailer(Mailer):
    """Any SMTP server (Gmail, Outlook, Fastmail, SES, a self-hosted relay...).

    security: "ssl" (implicit TLS, default port 465) or
              "starttls" (default port 587).  Plaintext is not supported.
    """

    DEFAULT_PORTS = {"ssl": 465, "starttls": 587}

    def __init__(self, host, user, password, sender, port=None, security="ssl"):
        if security not in self.DEFAULT_PORTS:
            raise ValueError(f"smtp security must be one of {sorted(self.DEFAULT_PORTS)}")
        if not host:
            raise ValueError("smtp requires a host (--smtp-host or SMTP_HOST)")
        if not user or not password:
            raise ValueError("smtp requires SMTP_USER and SMTP_PASSWORD")
        if not sender:
            raise ValueError("smtp requires a sender (--from or MAIL_FROM)")
        self.host, self.user, self.password = host, user, password
        self.sender = sender
        self.security = security
        self.port = int(port) if port else self.DEFAULT_PORTS[security]
        self._server = None

    def __enter__(self):
        ctx = ssl.create_default_context()
        try:
            if self.security == "ssl":
                server = smtplib.SMTP_SSL(self.host, self.port, context=ctx)
            else:
                server = smtplib.SMTP(self.host, self.port)
                server.starttls(context=ctx)
            self._server = server
            server.login(self.user, self.password)
        except (OSError, smtplib.SMTPException) as e:
            self._close()
            raise MailError(f"smtp connection/login failed: {e}") from e
        return self

    def _close(self):
        if self._server is not None:
            try:
                self._server.quit()
            except (OSError, smtplib.SMTPException):
                pass
            self._server = None

    def __exit__(self, *exc):
        self._close()
        return False

    def send(self, msg):
        try:
            self._server.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            raise MailError(f"smtp send failed: {e}") from e


def _post(url, body, headers):
    """POST bytes, return parsed JSON.  Isolated so tests can replace it."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read(500).decode("utf-8", "replace")
        raise MailError(f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}: {detail}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise MailError(f"request to {urllib.parse.urlsplit(url).netloc} failed: {e}") from e


class GmailApiMailer(Mailer):
    """Gmail REST API using an OAuth refresh token (scope: gmail.send).

    Needs a Google Cloud OAuth client and a refresh token granted for
    https://www.googleapis.com/auth/gmail.send.  From defaults to the
    authenticated account, so ``sender`` is optional.
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

    def __init__(self, client_id, client_secret, refresh_token, sender=None):
        if not (client_id and client_secret and refresh_token):
            raise ValueError(
                "gmail-api requires GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET "
                "and GMAIL_REFRESH_TOKEN"
            )
        self.client_id, self.client_secret = client_id, client_secret
        self.refresh_token = refresh_token
        self.sender = sender
        self._access_token = None

    def __enter__(self):
        body = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode()
        resp = _post(
            self.TOKEN_URL, body, {"Content-Type": "application/x-www-form-urlencoded"}
        )
        self._access_token = resp.get("access_token")
        if not self._access_token:
            raise MailError("gmail-api: token response had no access_token")
        return self

    def send(self, msg):
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        _post(
            self.SEND_URL,
            json.dumps({"raw": raw}).encode(),
            {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
        )


def _smtp_factory(env, opts):
    return SmtpMailer(
        host=opts.get("smtp_host") or env.get("SMTP_HOST"),
        port=opts.get("smtp_port") or env.get("SMTP_PORT"),
        security=opts.get("smtp_security") or env.get("SMTP_SECURITY") or "ssl",
        user=env.get("SMTP_USER"),
        password=env.get("SMTP_PASSWORD"),
        sender=opts.get("sender") or env.get("MAIL_FROM") or env.get("SMTP_USER"),
    )


def _gmail_api_factory(env, opts):
    return GmailApiMailer(
        client_id=env.get("GMAIL_CLIENT_ID"),
        client_secret=env.get("GMAIL_CLIENT_SECRET"),
        refresh_token=env.get("GMAIL_REFRESH_TOKEN"),
        sender=opts.get("sender") or env.get("MAIL_FROM"),
    )


PROVIDERS = {"smtp": _smtp_factory, "gmail-api": _gmail_api_factory}


def create_mailer(provider, env=None, **opts):
    """Build a provider from the environment plus optional overrides.

    opts: sender, smtp_host, smtp_port, smtp_security (None values ignored).
    """
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; choose from {sorted(PROVIDERS)}")
    return PROVIDERS[provider](os.environ if env is None else env, opts)


def send_all(mailer, messages):
    """Send every message; on failure say who already got theirs."""
    sent = []
    with mailer:
        for msg in messages:
            try:
                mailer.send(msg)
            except MailError as e:
                done = ", ".join(sent) or "nobody"
                raise MailError(
                    f"{e} (failed sending to {msg['To']}; already sent to: {done})"
                ) from e
            sent.append(str(msg["To"]))
    return len(sent)
