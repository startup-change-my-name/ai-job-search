import asyncio

import httpx
import pytest

from job_control_api import probes
from job_control_api.probes import HttpAirflowProbe, SystemProbe


class PassingDatabase:
    async def ping(self) -> None:
        return None


class FailingDatabase:
    async def ping(self) -> None:
        raise ConnectionError("database refused connection")


class NeverCompletingDatabase:
    def __init__(self) -> None:
        self.cancelled = False

    async def ping(self) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True


class SlowCancellationDatabase:
    def __init__(self) -> None:
        self.cancellation_started = asyncio.Event()
        self.release_cleanup = asyncio.Event()

    async def ping(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancellation_started.set()
            await self.release_cleanup.wait()


class HealthyAirflow:
    async def health(self) -> dict:
        return {
            "metadatabase": {"status": "healthy"},
            "scheduler": {"status": "healthy"},
            "triggerer": {"status": "healthy"},
            "dag_processor": {"status": "healthy"},
        }


class DegradedAirflow:
    async def health(self) -> dict:
        return {
            "metadatabase": {"status": "healthy"},
            "scheduler": {"status": "unhealthy"},
            "triggerer": {"status": "healthy"},
            "dag_processor": {"status": "healthy"},
        }


class FailingAirflow:
    async def health(self) -> dict:
        raise httpx.ConnectError("airflow unavailable")


@pytest.mark.asyncio
async def test_collect_reports_healthy_dependencies():
    result = await SystemProbe(PassingDatabase(), HealthyAirflow()).collect()
    assert {item.name: item.state for item in result.services} == {
        "postgres": "healthy",
        "airflow": "healthy",
    }


@pytest.mark.asyncio
async def test_collect_degrades_database_without_hiding_airflow():
    result = await SystemProbe(FailingDatabase(), HealthyAirflow()).collect()
    states = {item.name: item.state for item in result.services}
    assert states == {"postgres": "unavailable", "airflow": "healthy"}


@pytest.mark.asyncio
async def test_collect_times_out_database_without_hiding_healthy_airflow(monkeypatch):
    database = NeverCompletingDatabase()
    assert 0 < probes.DEPENDENCY_PROBE_TIMEOUT_SECONDS < 3.0
    monkeypatch.setattr(probes, "DEPENDENCY_PROBE_TIMEOUT_SECONDS", 0.01, raising=False)

    result = await asyncio.wait_for(
        SystemProbe(database, HealthyAirflow()).collect(),
        timeout=0.2,
    )

    assert [
        (item.name, item.state, item.detail)
        for item in result.services
    ] == [
        ("postgres", "unavailable", "TimeoutError"),
        ("airflow", "healthy", None),
    ]
    assert database.cancelled


@pytest.mark.asyncio
async def test_collect_deadline_does_not_wait_for_database_cancellation_cleanup(
    monkeypatch,
):
    database = SlowCancellationDatabase()
    probe = SystemProbe(database, HealthyAirflow())
    monkeypatch.setattr(probes, "DEPENDENCY_PROBE_TIMEOUT_SECONDS", 0.01)

    try:
        result = await asyncio.wait_for(probe.collect(), timeout=0.2)

        assert [
            (item.name, item.state, item.detail)
            for item in result.services
        ] == [
            ("postgres", "unavailable", "TimeoutError"),
            ("airflow", "healthy", None),
        ]
        assert database.cancellation_started.is_set()
        cleanup_tasks = tuple(probe._cleanup_tasks)
        assert len(cleanup_tasks) == 1
    finally:
        database.release_cleanup.set()

    await asyncio.wait_for(asyncio.gather(*cleanup_tasks), timeout=0.2)
    await asyncio.sleep(0)
    assert not probe._cleanup_tasks


@pytest.mark.asyncio
async def test_collect_reports_degraded_airflow_components():
    result = await SystemProbe(PassingDatabase(), DegradedAirflow()).collect()
    states = {item.name: item.state for item in result.services}
    assert states == {"postgres": "healthy", "airflow": "degraded"}


@pytest.mark.asyncio
async def test_collect_reports_unavailable_airflow():
    result = await SystemProbe(PassingDatabase(), FailingAirflow()).collect()
    statuses = {item.name: item for item in result.services}
    assert statuses["airflow"].state == "unavailable"
    assert statuses["airflow"].detail == "ConnectError"


@pytest.mark.asyncio
async def test_http_airflow_probe_returns_json_response(monkeypatch):
    async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://airflow.test/health"
        return httpx.Response(200, json={"scheduler": {"status": "healthy"}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )

    result = await HttpAirflowProbe("http://airflow.test/health").health()
    assert result == {"scheduler": {"status": "healthy"}}


@pytest.mark.asyncio
async def test_http_airflow_probe_raises_for_http_errors(monkeypatch):
    async_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(503, request=request))
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await HttpAirflowProbe("http://airflow.test/health").health()
