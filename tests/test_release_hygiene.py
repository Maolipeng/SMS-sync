import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseHygieneTests(unittest.TestCase):
    def test_sensitive_runtime_files_are_ignored(self):
        ignored = (ROOT / ".gitignore").read_text()
        for item in (".env", "*.sqlite3", "*.db", "*.log", ".secrets/", ".playwright-cli/", "output/"):
            self.assertIn(item, ignored)

    def test_example_configuration_has_no_credentials(self):
        example = (ROOT / ".env.example").read_text()
        self.assertEqual(example.split("TELEGRAM_BOT_TOKEN=", 1)[1].splitlines()[0], "")

    def test_source_does_not_hardcode_a_bot_token(self):
        source = "\n".join(path.read_text() for path in ROOT.glob("*.py"))
        self.assertNotRegex(source, r"\d{7,}:AA[A-Za-z0-9_-]{20,}")

    def test_keychain_write_does_not_pass_secret_in_process_arguments(self):
        source = (ROOT / "sms_bridge.py").read_text()
        self.assertIn("SecKeychainAddGenericPassword", source)
        self.assertNotIn('"add-generic-password"', source)


if __name__ == "__main__":
    unittest.main()
