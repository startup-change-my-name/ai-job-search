from pathlib import Path

from airflow.models import DagBag


def test_platform_health_dag_imports_without_errors():
    dag_dir = Path(__file__).resolve().parents[1] / "dags"
    bag = DagBag(dag_folder=str(dag_dir))
    assert bag.import_errors == {}
    dag = bag.dags.get("platform_health")
    assert dag is not None
    assert dag.schedule is None
    assert dag.catchup is False
    assert set(dag.task_ids) == {"heartbeat"}
