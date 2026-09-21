from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from job_control_api.main import create_app
from job_control_api.models import ServiceStatus, SystemStatus
from job_control_api.settings import Settings


class FakeProbe:
    def __init__(self) -> None:
        self.calls = 0

    async def collect(self) -> SystemStatus:
        self.calls += 1
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


def test_settings_reject_empty_proxy_token():
    with pytest.raises(ValidationError, match="internal_proxy_token"):
        Settings(
            database_url="postgresql+psycopg://job_control:test@postgres/job_control",
            airflow_health_url="http://airflow-api-server:8080/api/v2/monitor/health",
            internal_proxy_token="",
        )


def test_readiness_returns_probe_status_without_authentication():
    client = TestClient(create_app(settings(), FakeProbe()))
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["services"][0]["name"] == "postgres"


def test_system_status_rejects_missing_proxy_token():
    client = TestClient(create_app(settings(), FakeProbe()))
    assert client.get("/api/v1/system/status").status_code == 401


def test_system_status_rejects_incorrect_token_before_collecting_status():
    probe = FakeProbe()
    client = TestClient(create_app(settings(), probe))
    response = client.get(
        "/api/v1/system/status",
        headers={"X-Job-Control-Proxy-Token": "incorrect-token"},
    )
    assert response.status_code == 401
    assert probe.calls == 0


def test_system_status_rejects_non_ascii_token():
    probe = FakeProbe()
    client = TestClient(create_app(settings(), probe))
    response = client.get(
        "/api/v1/system/status",
        headers=[(b"X-Job-Control-Proxy-Token", b"malformed-\xff")],
    )
    assert response.status_code == 401
    assert probe.calls == 0


def test_system_status_accepts_exact_proxy_token():
    client = TestClient(create_app(settings(), FakeProbe()))
    response = client.get(
        "/api/v1/system/status",
        headers={"X-Job-Control-Proxy-Token": "test-proxy-token"},
    )
    assert response.status_code == 200
    assert response.json()["services"][0]["name"] == "postgres"
