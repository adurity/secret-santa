import io
import random
import secrets
import unittest
from collections import Counter
from contextlib import redirect_stdout
from unittest import mock

import secret_santa as ss

PAIRS = [("Alice", "Bob"), ("Mickey", "Minnie"), ("Tom", "Jerry"), ("Ann", "Zed")]


def check_valid(tc, pairs, result):
    partner = {}
    for a, b in pairs:
        partner[a], partner[b] = b, a
    tc.assertEqual(set(result), set(partner))
    received = Counter()
    for giver, gifts in result.items():
        tc.assertEqual(len(gifts), 2)
        tc.assertEqual(len(set(gifts)), 2, "recipients must be distinct")
        tc.assertIn(partner[giver], gifts)
        tc.assertNotIn(giver, gifts)
        received.update(gifts)
    tc.assertEqual(set(received), set(partner))
    tc.assertTrue(all(c == 2 for c in received.values()), received)


class ParseTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(
            ss.parse_pairs("Alice Bob\n\n# c\n  Mickey   Minnie \n"),
            [("Alice", "Bob"), ("Mickey", "Minnie")],
        )

    def test_bad_input(self):
        for text in ["Alice", "A B C", "A B\nB C", "A A", "A B\nC A"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                ss.parse_pairs(text)


class AssignTests(unittest.TestCase):
    def test_constraints_many_runs(self):
        for _ in range(500):
            check_valid(self, PAIRS, ss.assign(PAIRS))

    def test_minimum_size_two_pairs(self):
        pairs = [("Alice", "Bob"), ("Mickey", "Minnie")]
        for _ in range(100):
            res = ss.assign(pairs)
            check_valid(self, pairs, res)
            self.assertIn(res["Alice"][1], ("Mickey", "Minnie"))

    def test_large(self):
        pairs = [(f"a{i}", f"b{i}") for i in range(200)]
        check_valid(self, pairs, ss.assign(pairs))

    def test_too_few_pairs(self):
        for pairs in ([], [("A", "B")]):
            with self.assertRaises(ValueError):
                ss.assign(pairs)

    def test_duplicate_names_rejected(self):
        with self.assertRaises(ValueError):
            ss.assign([("A", "B"), ("A", "C")])

    def test_partner_listed_first_and_input_order(self):
        res = ss.assign(PAIRS)
        self.assertEqual(list(res)[:2], ["Alice", "Bob"])
        self.assertEqual(res["Alice"][0], "Bob")
        self.assertEqual(res["Bob"][0], "Alice")

    def test_uses_system_csprng_by_default(self):
        with mock.patch.object(
            secrets.SystemRandom, "shuffle", autospec=True,
            side_effect=secrets.SystemRandom.shuffle,
        ) as m:
            ss.assign(PAIRS)
        self.assertTrue(m.called)
        self.assertNotIn("random", ss.__dict__, "must not import the Mersenne Twister module")

    def test_actually_random(self):
        outcomes = {tuple(ss.assign(PAIRS).items()) for _ in range(200)}
        self.assertGreater(len(outcomes), 5)

    def test_deterministic_with_injected_rng(self):
        a = ss.assign(PAIRS, random.Random(1))
        b = ss.assign(PAIRS, random.Random(1))
        self.assertEqual(a, b)
        check_valid(self, PAIRS, a)

    def test_roughly_uniform_four_people(self):
        # Two couples: Alice's extra is Mickey or Minnie, ~50/50.
        pairs = [("Alice", "Bob"), ("Mickey", "Minnie")]
        c = Counter(ss.assign(pairs)["Alice"][1] for _ in range(2000))
        self.assertGreater(min(c.values()), 800)


class CliTests(unittest.TestCase):
    def test_output_format(self):
        buf = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("Alice Bob\nMickey Minnie\n")), \
                redirect_stdout(buf):
            self.assertEqual(ss.main([]), 0)
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("Alice: Bob "))
        self.assertTrue(lines[1].startswith("Bob: Alice "))

    def test_error_exit_code(self):
        with mock.patch("sys.stdin", io.StringIO("Alice Bob\n")), \
                mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(ss.main([]), 1)


if __name__ == "__main__":
    unittest.main()
