# CLAUDE.md

Paired Secret Santa script: each person gives two gifts (their partner + one
random other person) and receives exactly two. Can email each giver.

## Layout
- `secret_santa.py` — config parsing/validation (`load_config`), assignment (`assign`), message building, CLI.
- `mailers.py` — mail providers (`SmtpMailer`, `GmailApiMailer`), `PROVIDERS` registry, `create_mailer`, `send_all`.
- `test_secret_santa.py`, `test_mailers.py` — `unittest`-style tests, also run by pytest.
- `pairs.example.toml` — sample input. Real `pairs.toml` is git-ignored (contains emails).

## Commands
- Run tests: `python3 -m pytest` (or `python3 -m unittest`)
- Run script: `python3 secret_santa.py pairs.toml` (reads stdin if no file given)
- Send: `python3 secret_santa.py --send smtp|gmail-api pairs.toml`

## Invariants — don't break these
- Randomness must come from `secrets.SystemRandom` (OS CSPRNG). Never import or use the `random` module in `secret_santa.py`; a test enforces this. Tests may inject `random.Random` via the `rng` parameter for determinism.
- The extra-gift assignment is a permutation where nobody gives to themselves or their partner. This guarantees everyone receives exactly two gifts and gives to two distinct people.
- Keep it uniform: invalid shuffles are rejected and redone, not patched up.
- Input is TOML: `pairs = [[id, id], ...]` (before the tables) plus `[participants.<id>]` with `name` and `email`. Validation is strict (unknown keys, unpaired people, unknown/duplicate ids, duplicate names, bad emails, control characters in names). `assign` works on ids only.
- Print output is `Name: Partner Extra`, partner first, pair order.
- Needs at least two pairs.
- `--send` must not print assignments. Each email contains only that giver's recipients.
- Secrets (SMTP password, OAuth client secret/refresh token) come from environment variables only, never CLI args or files. Don't log them or include them in error messages.
- SMTP is TLS-only (`ssl`/`starttls`); no plaintext option.
- Providers connect/authenticate in `__enter__` so credential errors surface before any email is sent.
- Tests must mock SMTP and HTTP (`smtplib.SMTP*`, `mailers._post`); never send real mail or touch the network.

## Style
- Python 3.11+, stdlib only, no new dependencies without a good reason.
- Any behaviour change needs a matching test.
