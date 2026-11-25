#!/usr/bin/env python3
"""Paired Secret Santa: everyone gives two gifts and receives two gifts.

Input: one pair per line: name, email, name, email (whitespace-separated;
blank lines and lines starting with '#' are ignored).

    Alice alice@example.com Bob bob@example.com
    Mickey mickey@example.com Minnie minnie@example.com

Output: one line per person, partner first, then the random extra recipient.

    Alice: Bob Mickey
    Bob: Alice Minnie

With ``--send`` the assignments are NOT printed; each person is emailed their
own two recipients through Gmail SMTP instead (see ``send_messages``).

Each person gives to their partner (so each person receives one gift from
their partner) plus one other person.  The "extra" gifts form a random
permutation of everyone in which nobody gives to themselves or their
partner, so everyone receives exactly one extra gift: two gifts in total.

Randomness comes from ``secrets.SystemRandom`` (the OS CSPRNG).
"""

import argparse
import os
import re
import secrets
import smtplib
import sys
from email.message import EmailMessage

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GMAIL_HOST, GMAIL_PORT = "smtp.gmail.com", 465


def parse_pairs(text):
    """Parse text into ``(pairs, emails)``.

    ``pairs`` is a list of (name, name) tuples; ``emails`` maps name -> email.
    """
    pairs = []
    emails = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = line.split()
        if len(tokens) != 4:
            raise ValueError(
                f"line {lineno}: expected 'name email name email', "
                f"got {len(tokens)} fields"
            )
        pair = []
        for name, email in (tokens[0:2], tokens[2:4]):
            if name in emails:
                raise ValueError(f"line {lineno}: duplicate name {name!r}")
            if not EMAIL_RE.match(email):
                raise ValueError(f"line {lineno}: invalid email {email!r}")
            emails[name] = email
            pair.append(name)
        pairs.append(tuple(pair))
    return pairs, emails


def assign(pairs, rng=None):
    """Return {giver: (partner, extra_recipient)} for every person.

    ``rng`` must provide ``shuffle``; defaults to the OS CSPRNG.  Passing a
    custom one is intended for tests only.
    """
    if len(pairs) < 2:
        raise ValueError("need at least two pairs")
    if rng is None:
        rng = secrets.SystemRandom()

    partner = {}
    for a, b in pairs:
        if a == b or a in partner or b in partner:
            raise ValueError(f"invalid or duplicate name in pair {a!r}, {b!r}")
        partner[a] = b
        partner[b] = a

    people = list(partner)  # input order
    targets = people[:]
    # Rejection sampling keeps the permutation uniform over all valid ones.
    # A random permutation is valid with probability ~e^-2, so this is fast.
    while True:
        rng.shuffle(targets)
        if all(t != p and t != partner[p] for p, t in zip(people, targets)):
            break
    return {p: (partner[p], t) for p, t in zip(people, targets)}


def format_assignments(assignments):
    return "\n".join(f"{g}: {a} {b}" for g, (a, b) in assignments.items())


def build_messages(assignments, emails, sender):
    """One EmailMessage per giver, containing only that giver's recipients."""
    messages = []
    for giver, (partner, extra) in assignments.items():
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = emails[giver]
        msg["Subject"] = "Your Secret Santa assignments"
        msg.set_content(
            f"Hi {giver},\n\n"
            "You are giving two gifts this year:\n"
            f"  1. {partner}\n"
            f"  2. {extra}\n\n"
            "Keep it secret!\n"
        )
        messages.append(msg)
    return messages


def send_messages(messages, user, app_password, smtp_factory=None):
    """Send via Gmail SMTP using an app password (not your account password)."""
    smtp_factory = smtp_factory or smtplib.SMTP_SSL
    with smtp_factory(GMAIL_HOST, GMAIL_PORT) as server:
        server.login(user, app_password)
        for msg in messages:
            server.send_message(msg)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Paired Secret Santa.")
    ap.add_argument("pairs_file", nargs="?", help="pairs file (default: stdin)")
    ap.add_argument(
        "--send",
        action="store_true",
        help="email each giver via Gmail instead of printing assignments; "
        "needs GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the environment",
    )
    args = ap.parse_args(argv)
    try:
        if args.send:
            user = os.environ.get("GMAIL_ADDRESS")
            password = os.environ.get("GMAIL_APP_PASSWORD")
            if not user or not password:
                raise ValueError(
                    "--send requires GMAIL_ADDRESS and GMAIL_APP_PASSWORD"
                )
        if args.pairs_file:
            with open(args.pairs_file) as f:
                text = f.read()
        else:
            text = sys.stdin.read()
        pairs, emails = parse_pairs(text)
        assignments = assign(pairs)
        if args.send:
            messages = build_messages(assignments, emails, user)
            send_messages(messages, user, password)
            print(f"Sent {len(messages)} emails.")
        else:
            print(format_assignments(assignments))
    except (OSError, ValueError, smtplib.SMTPException) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
