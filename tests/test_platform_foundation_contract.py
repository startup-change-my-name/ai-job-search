import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "platform" / "runtime.env.template"
README = ROOT / "platform" / "README.md"
GITIGNORE = ROOT / ".gitignore"

REQUIRED_KEYS = {
    "POSTGRES_PASSWORD",
    "INTERNAL_PROXY_TOKEN",
    "TAILSCALE_ALLOWED_LOGINS",
    "PRIVATE_WORKSPACE_PATH",
    "AIRFLOW_UID",
    "TZ",
}


class PlatformFoundationContractTests(unittest.TestCase):
    def test_runtime_template_declares_required_keys_without_real_secrets(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        keys = {
            match.group(1)
            for match in re.finditer(r"^([A-Z][A-Z0-9_]*)=", text, re.MULTILINE)
        }
        self.assertTrue(REQUIRED_KEYS.issubset(keys))
        emails = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
        self.assertEqual(emails, ["you@example.com"])

    def test_readme_requires_private_runtime_file_and_loopback_access(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("ai-job-search-private/config/job-control/runtime.env", text)
        self.assertIn("127.0.0.1:3000", text)
        self.assertIn("Tailscale Serve", text)
        self.assertIn("Funnel", text)

    def test_runtime_state_and_logs_are_ignored(self):
        rules = GITIGNORE.read_text(encoding="utf-8").splitlines()
        self.assertIn("platform/runtime/", rules)
        self.assertIn("platform/**/logs/", rules)


if __name__ == "__main__":
    unittest.main()
