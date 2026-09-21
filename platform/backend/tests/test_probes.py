import pytest

from job_control_api.probes import SystemProbe


class PassingDatabase:
    async def ping(self) -> None:
        return None


class FailingDatabase:
    async def ping(self) -> None:
        raise ConnectionError("database refused connection")


class HealthyAirflow:
    async def health(self) -> dict:
        return {
            "metadatabase": {"status": "healthy"},
            "scheduler": {"status": "healthy"},
            "triggerer": {"status": "healthy"},
            "dag_processor": {"status": "healthy"},
        }


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
