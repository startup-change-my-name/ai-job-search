from datetime import datetime, timezone

from fastapi.testclient import TestClient

from job_control_api.main import create_app
from job_control_api.models import ServiceStatus, SystemStatus
from job_control_api.settings import Settings


class FakeProbe:
    async def collect(self) -> SystemStatus:
        now = datetime.now(timezone.utc)
        return SystemStatus(
            generated_at=now,
            services=[ServiceStatus(name="postgres", state="healthy", checked_at=now)],
        )


def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://job_control:test@postgres/job_control",
        airflow_health_url="http://airflow-api-server:8080/api/v2/monitor/health",
        internal_proxy_token="test-proxy-token",
    )


def test_liveness_is_unprotected_and_contains_utc_timestamp():
    client = TestClient(create_app(settings(), FakeProbe()))
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checked_at"].endswith("Z")


def test_system_status_rejects_missing_proxy_token():
    client = TestClient(create_app(settings(), FakeProbe()))
    assert client.get("/api/v1/system/status").status_code == 401


def test_system_status_accepts_exact_proxy_token():
    client = TestClient(create_app(settings(), FakeProbe()))
    response = client.get(
        "/api/v1/system/status",
        headers={"X-Job-Control-Proxy-Token": "test-proxy-token"},
    )
    assert response.status_code == 200
    assert response.json()["services"][0]["name"] == "postgres"
