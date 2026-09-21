import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "platform" / "compose.yaml"


class PlatformComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        cls.services = cls.data["services"]

    def test_expected_services_exist(self):
        self.assertEqual(set(self.services), {
            "postgres", "redis", "airflow-init", "airflow-api-server",
            "airflow-scheduler", "airflow-dag-processor", "airflow-worker",
            "airflow-triggerer", "api", "web",
        })

    def test_only_web_publishes_a_loopback_port(self):
        published = {name: service["ports"] for name, service in self.services.items()
                     if service.get("ports")}
        self.assertEqual(published, {"web": ["127.0.0.1:${WEB_PORT:-3000}:3000"]})

    def test_private_workspace_mount_is_read_only_and_api_only(self):
        mount = "${PRIVATE_WORKSPACE_PATH}:/workspace/private:ro"
        self.assertIn(mount, self.services["api"]["volumes"])
        for name, service in self.services.items():
            if name != "api":
                self.assertNotIn(mount, service.get("volumes", []))

    def test_no_host_control_or_literal_secrets(self):
        serialized = COMPOSE.read_text(encoding="utf-8")
        for forbidden in ("docker.sock", "change-me", "you@example.com"):
            self.assertNotIn(forbidden, serialized)
        for service in self.services.values():
            self.assertFalse(service.get("privileged", False))
            self.assertNotEqual(service.get("network_mode"), "host")

    def test_database_and_broker_are_isolated(self):
        self.assertEqual(self.services["postgres"]["networks"], ["data"])
        self.assertEqual(self.services["redis"]["networks"], ["control"])
        for name in ("data", "control"):
            self.assertTrue(self.data["networks"][name]["internal"])

    def test_all_long_running_services_have_health_checks(self):
        for name, service in self.services.items():
            if name == "airflow-init":
                self.assertEqual(service["restart"], "no")
                continue
            self.assertIn("test", service["healthcheck"], name)

    def test_airflow_services_wait_for_migrations(self):
        for name, service in self.services.items():
            if name.startswith("airflow-") and name != "airflow-init":
                self.assertEqual(service["depends_on"]["airflow-init"]["condition"],
                                 "service_completed_successfully")


if __name__ == "__main__":
    unittest.main()
