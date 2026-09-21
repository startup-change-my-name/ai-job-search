from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header

from .auth import require_proxy_token
from .models import SystemStatus
from .probes import SystemProbe, build_system_probe
from .settings import Settings


def create_app(settings: Settings | None = None, probe: SystemProbe | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    resolved_probe = probe or build_system_probe(
        resolved_settings.database_url,
        str(resolved_settings.airflow_health_url),
    )
    app = FastAPI(title="Job Control API", version="0.1.0")

    def authorize(x_job_control_proxy_token: str | None = Header(default=None)) -> None:
        require_proxy_token(resolved_settings, x_job_control_proxy_token)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {"status": "ok", "checked_at": checked_at}

    @app.get("/health/ready")
    async def ready() -> SystemStatus:
        return await resolved_probe.collect()

    @app.get(
        "/api/v1/system/status",
        response_model=SystemStatus,
        dependencies=[Depends(authorize)],
    )
    async def system_status() -> SystemStatus:
        return await resolved_probe.collect()

    return app
