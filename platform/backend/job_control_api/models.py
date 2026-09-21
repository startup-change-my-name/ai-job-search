from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ServiceStatus(BaseModel):
    name: str
    state: Literal["healthy", "degraded", "unavailable"]
    checked_at: datetime
    detail: str | None = None


class SystemStatus(BaseModel):
    generated_at: datetime
    services: list[ServiceStatus]
