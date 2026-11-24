#!/usr/bin/env python3
"""Paired Secret Santa: everyone gives two gifts and receives two gifts.

Input: one pair per line, two whitespace-separated names (blank lines and
lines starting with '#' are ignored).

    Alice Bob
    Mickey Minnie

Output: one line per person, partner first, then the random extra recipient.

    Alice: Bob Mickey
    Bob: Alice Minnie

Each person gives to their partner (so each person receives one gift from
their partner) plus one other person.  The "extra" gifts form a random
permutation of everyone in which nobody gives to themselves or their
partner, so everyone receives exactly one extra gift: two gifts in total.

Randomness comes from ``secrets.SystemRandom`` (the OS CSPRNG).
"""

import secrets
import sys


def parse_pairs(text):
    """Parse text into a list of (name, name) tuples, validating as we go."""
    pairs = []
    seen = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names = line.split()
        if len(names) != 2:
            raise ValueError(
                f"line {lineno}: expected exactly two names, got {len(names)}"
            )
        for name in names:
            if name in seen:
                raise ValueError(f"line {lineno}: duplicate name {name!r}")
            seen.add(name)
        pairs.append(tuple(names))
    return pairs


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


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1 or argv[:1] in (["-h"], ["--help"]):
        print("usage: secret_santa.py [pairs_file]   (reads stdin if omitted)")
        return 2
    try:
        text = open(argv[0]).read() if argv else sys.stdin.read()
        print(format_assignments(assign(parse_pairs(text))))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
