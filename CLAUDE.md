# CLAUDE.md

Paired Secret Santa script: each person gives two gifts (their partner + one
random other person) and receives exactly two.

## Layout
- `secret_santa.py` — the whole implementation (`parse_pairs`, `assign`, `format_assignments`, `main`). Standard library only.
- `test_secret_santa.py` — `unittest`-style tests, also run by pytest.

## Commands
- Run tests: `python3 -m pytest` (or `python3 -m unittest`)
- Run script: `python3 secret_santa.py pairs.txt` (reads stdin if no file given)

## Invariants — don't break these
- Randomness must come from `secrets.SystemRandom` (OS CSPRNG). Never import or use the `random` module in `secret_santa.py`; a test enforces this. Tests may inject `random.Random` via the `rng` parameter for determinism.
- The extra-gift assignment is a permutation where nobody gives to themselves or their partner. This guarantees everyone receives exactly two gifts and gives to two distinct people.
- Keep it uniform: invalid shuffles are rejected and redone, not patched up.
- Output format is `Name: Partner Extra`, partner first, in input order.
- Needs at least two pairs; names are whitespace-free and unique.
- Input line format is `name email name email`. `parse_pairs` returns `(pairs, emails)`; `assign` only sees names.
- `--send` emails each giver (Gmail SMTP, credentials from `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` env vars, never CLI args or files) and must not print assignments. Each email contains only that giver's recipients. Tests must mock SMTP; never send real mail from tests.

## Style
- Python 3, stdlib only, no new dependencies without a good reason.
- Any behaviour change needs a matching test.
