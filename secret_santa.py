#!/usr/bin/env python3
"""Paired Secret Santa: everyone gives two gifts and receives two gifts.

Input is a TOML file (Python 3.11+): who the participants are, and who is
paired with whom.  Participants are keyed by a stable id; pairs refer to ids.

    pairs = [
      ["alice", "bob"],
      ["mickey", "minnie"],
    ]

    [participants.alice]
    name = "Alice"
    email = "alice@example.com"
    ...

Output: one line per person, partner first, then the random extra recipient.

    Alice: Bob Mickey
    Bob: Alice Minnie

With ``--send PROVIDER`` the assignments are NOT printed; each person is
emailed their own two recipients instead (providers: see ``mailers.py``).

Each person gives to their partner (so each person receives one gift from
their partner) plus one other person.  The "extra" gifts form a random
permutation of everyone in which nobody gives to themselves or their
partner, so everyone receives exactly one extra gift: two gifts in total.

Randomness comes from ``secrets.SystemRandom`` (the OS CSPRNG).
"""

import argparse
import re
import secrets
import sys
import tomllib
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage

import mailers

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
TOP_KEYS = {"participants", "pairs"}
PARTICIPANT_KEYS = {"name", "email"}


@dataclass(frozen=True)
class Participant:
    id: str
    name: str
    email: str


def load_config(text):
    """Parse and validate TOML text into ``(participants, pairs)``.

    ``participants`` maps id -> Participant; ``pairs`` is a list of
    (id, id) tuples.  Raises ValueError with a readable message.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"invalid TOML: {e}") from e

    unknown = set(data) - TOP_KEYS
    if unknown:
        raise ValueError(f"unknown top-level keys: {sorted(unknown)}")

    raw = data.get("participants")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("missing [participants.<id>] tables")

    participants = {}
    names = set()
    for pid, fields in raw.items():
        if not isinstance(fields, dict):
            raise ValueError(f"participant {pid!r} must be a table")
        unknown = set(fields) - PARTICIPANT_KEYS
        if unknown:
            raise ValueError(f"participant {pid!r}: unknown keys {sorted(unknown)}")
        name, email = fields.get("name"), fields.get("email")
        if not isinstance(name, str) or not name.strip() or CONTROL_RE.search(name):
            raise ValueError(f"participant {pid!r}: invalid or missing name")
        if not isinstance(email, str) or not EMAIL_RE.match(email) or CONTROL_RE.search(email):
            raise ValueError(f"participant {pid!r}: invalid or missing email")
        if name in names:
            raise ValueError(f"participant {pid!r}: duplicate name {name!r}")
        names.add(name)
        participants[pid] = Participant(pid, name, email)

    raw_pairs = data.get("pairs")
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise ValueError("missing 'pairs' list")
    pairs, seen = [], set()
    for i, pair in enumerate(raw_pairs, 1):
        if not (isinstance(pair, list) and len(pair) == 2
                and all(isinstance(p, str) for p in pair)):
            raise ValueError(f"pair #{i}: expected [id, id]")
        for pid in pair:
            if pid not in participants:
                raise ValueError(f"pair #{i}: unknown participant id {pid!r}")
            if pid in seen:
                raise ValueError(f"pair #{i}: {pid!r} appears in more than one pair")
            seen.add(pid)
        if pair[0] == pair[1]:
            raise ValueError(f"pair #{i}: {pair[0]!r} is paired with themselves")
        pairs.append(tuple(pair))

    unpaired = [p for p in participants if p not in seen]
    if unpaired:
        raise ValueError(f"participants not in any pair: {unpaired}")
    return participants, pairs


def assign(pairs, rng=None):
    """Return {giver: (partner, extra_recipient)} for every id in ``pairs``.

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
            raise ValueError(f"invalid or duplicate id in pair {a!r}, {b!r}")
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


def format_assignments(assignments, participants):
    name = lambda pid: participants[pid].name
    return "\n".join(
        f"{name(g)}: {name(a)} {name(b)}" for g, (a, b) in assignments.items()
    )


def build_messages(assignments, participants, sender=None):
    """One EmailMessage per giver, containing only that giver's recipients."""
    messages = []
    for giver, (partner, extra) in assignments.items():
        g = participants[giver]
        msg = EmailMessage()
        if sender:
            msg["From"] = sender
        msg["To"] = Address(display_name=g.name, addr_spec=g.email)
        msg["Subject"] = "Your Secret Santa assignments"
        msg.set_content(
            f"Hi {g.name},\n\n"
            "You are giving two gifts this year:\n"
            f"  1. {participants[partner].name}\n"
            f"  2. {participants[extra].name}\n\n"
            "Keep it secret!\n"
        )
        messages.append(msg)
    return messages


def main(argv=None):
    ap = argparse.ArgumentParser(description="Paired Secret Santa.")
    ap.add_argument("config", nargs="?", help="TOML file (default: stdin)")
    ap.add_argument(
        "--send",
        metavar="PROVIDER",
        choices=sorted(mailers.PROVIDERS),
        help="email each giver via PROVIDER instead of printing assignments "
        f"({', '.join(sorted(mailers.PROVIDERS))}); credentials come from "
        "environment variables (see README)",
    )
    ap.add_argument("--from", dest="sender", help="From address (or MAIL_FROM)")
    ap.add_argument("--smtp-host", help="SMTP server (or SMTP_HOST)")
    ap.add_argument("--smtp-port", help="SMTP port (or SMTP_PORT)")
    ap.add_argument(
        "--smtp-security",
        choices=["ssl", "starttls"],
        help="SMTP transport security (or SMTP_SECURITY; default ssl)",
    )
    args = ap.parse_args(argv)
    try:
        mailer = None
        if args.send:
            mailer = mailers.create_mailer(
                args.send,
                sender=args.sender,
                smtp_host=args.smtp_host,
                smtp_port=args.smtp_port,
                smtp_security=args.smtp_security,
            )
        if args.config:
            with open(args.config, encoding="utf-8") as f:
                text = f.read()
        else:
            text = sys.stdin.read()
        participants, pairs = load_config(text)
        assignments = assign(pairs)
        if mailer:
            messages = build_messages(assignments, participants, mailer.sender)
            count = mailers.send_all(mailer, messages)
            print(f"Sent {count} emails.")
        else:
            print(format_assignments(assignments, participants))
    except (OSError, ValueError, mailers.MailError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
