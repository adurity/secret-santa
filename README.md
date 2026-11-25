# secret-santa

Simple script for Santa to get his gift recipient assignments right — with a twist.

Everyone gives **two** gifts and receives **two** gifts:

- one gift goes to their partner
- one gift goes to a random other person (never themselves or their partner)

## Usage

Requires Python 3.11+ (standard library only).

Describe your group in a TOML file (see [`pairs.example.toml`](pairs.example.toml)). People are listed once, keyed by an id, and pairs refer to those ids:

```toml
pairs = [
  ["alice",  "bob"],
  ["mickey", "minnie"],
]

[participants.alice]
name  = "Alice Smith"
email = "alice@example.com"

[participants.bob]
name  = "Bob Jones"
email = "bob@example.com"
# ... and so on for mickey and minnie
```

`pairs` must come before the `[participants.*]` tables. Every participant must be in exactly one pair; typos, unknown ids and duplicate names are reported as errors. Copy the example to `pairs.toml`, which is git-ignored because it contains email addresses.

Print the assignments (partner first, then the random extra recipient):

```
python3 secret_santa.py pairs.toml
# or: cat pairs.toml | python3 secret_santa.py
```

```
Alice Smith: Bob Jones Minnie
Bob Jones: Alice Smith Mickey
Mickey: Minnie Bob Jones
Minnie: Mickey Alice Smith
```

## Emailing the assignments

`--send PROVIDER` emails each person only their own two recipients. Assignments are **not** printed in this mode, so the organiser stays surprised too. Credentials are read from environment variables only, never from arguments.

If a send fails partway, the error lists who already got their email. Assignments are random on every run, so don't just re-run; email the rest by hand or tell everyone to ignore the earlier email and re-run.

### `smtp` — any SMTP server (fallback, works everywhere)

```
export SMTP_USER=you@example.org
export SMTP_PASSWORD=...
python3 secret_santa.py --send smtp --smtp-host smtp.example.org pairs.toml
```

| Setting | Flag | Env var | Default |
|---|---|---|---|
| Server | `--smtp-host` | `SMTP_HOST` | required |
| Port | `--smtp-port` | `SMTP_PORT` | 465 (ssl) / 587 (starttls) |
| Security | `--smtp-security ssl\|starttls` | `SMTP_SECURITY` | `ssl` |
| Login | | `SMTP_USER`, `SMTP_PASSWORD` | required |
| From | `--from` | `MAIL_FROM` | `SMTP_USER` |

Plaintext SMTP is deliberately unsupported. Examples: Gmail `smtp.gmail.com` (needs an app password; requires 2-step verification), Outlook `smtp.office365.com` with `--smtp-security starttls`.

### `gmail-api` — Gmail REST API with OAuth

Sends with the narrow `gmail.send` scope, so the credential can't read your mailbox, and works on Workspace accounts that disable app passwords. Setup: create an OAuth client in Google Cloud, enable the Gmail API, and obtain a refresh token for `https://www.googleapis.com/auth/gmail.send` (e.g. with the OAuth Playground).

```
export GMAIL_CLIENT_ID=...
export GMAIL_CLIENT_SECRET=...
export GMAIL_REFRESH_TOKEN=...
python3 secret_santa.py --send gmail-api pairs.toml
```

`--from` / `MAIL_FROM` is optional here; Gmail uses the authenticated account.

### Adding a provider

Subclass `Mailer` in `mailers.py` (`__enter__` to connect/authenticate, `send(msg)`), then register a factory in `PROVIDERS`.

## Rules and guarantees

- Everyone gives to exactly two distinct people, one of whom is their partner.
- Everyone receives exactly two gifts.
- Random choices use `secrets.SystemRandom` (the OS cryptographic RNG), and every valid arrangement is equally likely.
- At least two pairs are required. Display names must be unique (they may contain spaces); emails must look like `user@host.tld`.

## Tests

```
python3 -m pytest
```

No dependencies beyond the Python 3.11+ standard library (pytest is optional; `python3 -m unittest` works too). Tests never touch the network; SMTP and HTTP are mocked.
