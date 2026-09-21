from datetime import datetime, timezone
from typing import Protocol

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .models import ServiceStatus, SystemStatus


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

    async def collect(self) -> SystemStatus:
        now = datetime.now(timezone.utc)
        services: list[ServiceStatus] = []
        try:
            await self.database.ping()
            services.append(ServiceStatus(name="postgres", state="healthy", checked_at=now))
        except Exception as exc:
            services.append(
                ServiceStatus(
                    name="postgres",
                    state="unavailable",
                    checked_at=now,
                    detail=type(exc).__name__,
                )
            )
        try:
            payload = await self.airflow.health()
            states = [
                payload.get(name, {}).get("status")
                for name in ("metadatabase", "scheduler", "triggerer", "dag_processor")
            ]
            state = "healthy" if all(value == "healthy" for value in states) else "degraded"
            services.append(ServiceStatus(name="airflow", state=state, checked_at=now))
        except Exception as exc:
            services.append(
                ServiceStatus(
                    name="airflow",
                    state="unavailable",
                    checked_at=now,
                    detail=type(exc).__name__,
                )
            )
        return SystemStatus(generated_at=now, services=services)


def build_system_probe(database_url: str, airflow_health_url: str) -> SystemProbe:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return SystemProbe(
        SqlAlchemyDatabaseProbe(engine),
        HttpAirflowProbe(airflow_health_url),
    )
