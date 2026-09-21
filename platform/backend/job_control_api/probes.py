import asyncio
from datetime import datetime, timezone
from typing import Protocol

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .models import ServiceStatus, SystemStatus


# Leave response-processing headroom inside verify-stack.sh's three-second request limit.
DEPENDENCY_PROBE_TIMEOUT_SECONDS = 2.0


class DatabaseProbe(Protocol):
    async def ping(self) -> None: ...


class AirflowProbe(Protocol):
    async def health(self) -> dict: ...


class SqlAlchemyDatabaseProbe:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))


class HttpAirflowProbe:
    def __init__(self, url: str):
        self.url = url

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            return response.json()


class SystemProbe:
    def __init__(self, database: DatabaseProbe, airflow: AirflowProbe):
        self.database = database
        self.airflow = airflow

    async def _database_status(self, checked_at: datetime) -> ServiceStatus:
        try:
            await asyncio.wait_for(
                self.database.ping(),
                timeout=DEPENDENCY_PROBE_TIMEOUT_SECONDS,
            )
            return ServiceStatus(name="postgres", state="healthy", checked_at=checked_at)
        except Exception as exc:
            return ServiceStatus(
                name="postgres",
                state="unavailable",
                checked_at=checked_at,
                detail=type(exc).__name__,
            )

    async def _airflow_status(self, checked_at: datetime) -> ServiceStatus:
        try:
            payload = await asyncio.wait_for(
                self.airflow.health(),
                timeout=DEPENDENCY_PROBE_TIMEOUT_SECONDS,
            )
            states = [
                payload.get(name, {}).get("status")
                for name in ("metadatabase", "scheduler", "triggerer", "dag_processor")
            ]
            state = "healthy" if all(value == "healthy" for value in states) else "degraded"
            return ServiceStatus(name="airflow", state=state, checked_at=checked_at)
        except Exception as exc:
            return ServiceStatus(
                name="airflow",
                state="unavailable",
                checked_at=checked_at,
                detail=type(exc).__name__,
            )

    async def collect(self) -> SystemStatus:
        now = datetime.now(timezone.utc)
        postgres, airflow = await asyncio.gather(
            self._database_status(now),
            self._airflow_status(now),
        )
        return SystemStatus(generated_at=now, services=[postgres, airflow])


def build_system_probe(database_url: str, airflow_health_url: str) -> SystemProbe:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return SystemProbe(
        SqlAlchemyDatabaseProbe(engine),
        HttpAirflowProbe(airflow_health_url),
    )
