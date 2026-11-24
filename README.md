# secret-santa

Simple script for Santa to get his gift recipient assignments right — with a twist.

Everyone gives **two** gifts and receives **two** gifts:

- one gift goes to their partner
- one gift goes to a random other person (never themselves or their partner)

## Usage

Put one pair per line in a file (blank lines and `#` comments are ignored):

```
Alice Bob
Mickey Minnie
```

Then run:

```
python3 secret_santa.py pairs.txt
# or
cat pairs.txt | python3 secret_santa.py
```

Example output (partner first, then the random extra recipient):

```
Alice: Bob Minnie
Bob: Alice Mickey
Mickey: Minnie Bob
Minnie: Mickey Alice
```

## Rules and guarantees

- Everyone gives to exactly two distinct people, one of whom is their partner.
- Everyone receives exactly two gifts.
- Random choices use `secrets.SystemRandom` (the OS cryptographic RNG), and every valid arrangement is equally likely.
- At least two pairs are required. Names must be unique and contain no spaces.

## Tests

```
python3 -m pytest
```

No dependencies beyond the Python 3 standard library (pytest is optional; `python3 -m unittest` works too).
