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


def toml(pairs, extra=""):
    ids = [p for pair in pairs for p in pair]
    out = "pairs = " + repr([list(p) for p in pairs]).replace("'", '"') + "\n"
    for i in ids:
        out += f'[participants.{i}]\nname = "{i.title()}"\nemail = "{i}@x.com"\n'
    return out + extra


GOOD = toml([("alice", "bob"), ("mickey", "minnie")])


class ConfigTests(unittest.TestCase):
    def test_load(self):
        participants, pairs = ss.load_config(GOOD)
        self.assertEqual(pairs, [("alice", "bob"), ("mickey", "minnie")])
        self.assertEqual(
            participants["alice"], ss.Participant("alice", "Alice", "alice@x.com")
        )
        self.assertEqual(len(participants), 4)

    def test_names_may_have_spaces_and_unicode(self):
        text = toml([("a", "b"), ("c", "d")]).replace('"A"', '"Ana María O\'Neil"')
        participants, _ = ss.load_config(text)
        self.assertEqual(participants["a"].name, "Ana María O'Neil")

    def test_bad_config(self):
        base = toml([("a", "b"), ("c", "d")])
        cases = {
            "not toml": "this is = = not toml",
            "unknown top key": base + "extra = 1\n",
            "unknown participant key": base + '[participants.a.x]\n',
            "typo field": base.replace("email =", "emial =", 1),
            "bad email": base.replace("a@x.com", "nope"),
            "missing name": base.replace('name = "A"\n', "", 1),
            "control char in name": base.replace('"A"', '"A\\nBcc: evil@x.com"'),
            "unknown id in pair": base.replace('["a", "b"]', '["a", "zzz"]'),
            "id in two pairs": base.replace('["c", "d"]', '["a", "d"]'),
            "self pair": base.replace('["a", "b"]', '["a", "a"]'),
            "unpaired participant": base + '[participants.e]\nname = "E"\nemail = "e@x.com"\n',
            "duplicate display name": base.replace('"C"', '"A"'),
            "no pairs": base.replace("pairs = [[\"a\", \"b\"], [\"c\", \"d\"]]", "pairs = []"),
            "no participants": 'pairs = [["a","b"]]',
        }
        for label, text in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                ss.load_config(text)


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
    def run_main(self, argv, stdin=GOOD, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", env or {}, clear=True), \
                mock.patch("sys.stdin", io.StringIO(stdin)), \
                redirect_stdout(out), mock.patch("sys.stderr", err):
            code = ss.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_output_format(self):
        code, out, _ = self.run_main([])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("Alice: Bob "))
        self.assertTrue(lines[1].startswith("Bob: Alice "))

    def test_reads_file(self):
        import os, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write(GOOD)
        self.addCleanup(os.unlink, f.name)
        code, out, _ = self.run_main([f.name], stdin="")
        self.assertEqual((code, len(out.splitlines())), (0, 4))

    def test_error_exit_code(self):
        code, _, err = self.run_main([], stdin="garbage = = =")
        self.assertEqual(code, 1)
        self.assertIn("invalid TOML", err)

    def test_send_requires_credentials(self):
        for provider, needle in [("smtp", "SMTP"), ("gmail-api", "GMAIL_")]:
            code, out, err = self.run_main(["--send", provider])
            self.assertEqual(code, 1)
            self.assertIn(needle, err)
            self.assertEqual(out, "")

    def test_send_smtp_end_to_end_without_printing_assignments(self):
        env = {"SMTP_HOST": "mail.example.org", "SMTP_USER": "santa@example.org",
               "SMTP_PASSWORD": "pw"}
        server = mock.MagicMock()
        with mock.patch("smtplib.SMTP_SSL", return_value=server) as factory:
            code, out, _ = self.run_main(["--send", "smtp"], env=env)
        self.assertEqual(code, 0)
        self.assertEqual(factory.call_args[0], ("mail.example.org", 465))
        server.login.assert_called_once_with("santa@example.org", "pw")
        self.assertEqual(server.send_message.call_count, 4)
        self.assertEqual(out.strip(), "Sent 4 emails.")

    def test_send_gmail_api_end_to_end(self):
        env = {"GMAIL_CLIENT_ID": "i", "GMAIL_CLIENT_SECRET": "s",
               "GMAIL_REFRESH_TOKEN": "r"}
        with mock.patch("mailers._post", return_value={"access_token": "tok"}) as post:
            code, out, _ = self.run_main(["--send", "gmail-api"], env=env)
        self.assertEqual(code, 0)
        self.assertEqual(post.call_count, 1 + 4)  # token + 4 sends
        self.assertEqual(out.strip(), "Sent 4 emails.")


class EmailTests(unittest.TestCase):
    def test_build_messages(self):
        participants, pairs = ss.load_config(GOOD)
        result = ss.assign(pairs)
        msgs = ss.build_messages(result, participants, "santa@x.com")
        self.assertEqual(len(msgs), 4)
        for msg, (giver, gifts) in zip(msgs, result.items()):
            self.assertEqual(msg["To"].addresses[0].addr_spec, participants[giver].email)
            self.assertEqual(msg["From"], "santa@x.com")
            body = msg.get_content()
            for rid in gifts:
                self.assertIn(participants[rid].name, body)
            # nobody else's recipients leak into this message
            for other in set(result) - {giver, *gifts}:
                self.assertNotIn(f"  1. {participants[other].name}", body)
                self.assertNotIn(f"  2. {participants[other].name}", body)

    def test_from_omitted_when_no_sender(self):
        participants, pairs = ss.load_config(GOOD)
        msg = ss.build_messages(ss.assign(pairs), participants)[0]
        self.assertIsNone(msg["From"])


if __name__ == "__main__":
    unittest.main()
