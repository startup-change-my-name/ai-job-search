from datetime import datetime, timezone

from airflow.sdk import dag, task


@dag(
    dag_id="platform_health",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    tags=["platform", "health"],
)
def platform_health():
    @task
    def heartbeat() -> dict[str, str]:
        return {
            "status": "ok",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    heartbeat()


platform_health()
