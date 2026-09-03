import json
from adapters.catala_adapter import CatalaAdapter
from pathlib import Path

def test_validate_input_and_execute():
    adapter = CatalaAdapter()
    manifest_path = Path("examples/catala/manifest.json")
    manifest = json.loads(manifest_path.read_text())

    assert adapter.validate_manifest(manifest)["ok"]

    input_json = {"agent_revenu": 32000, "agent_enfants": 2, "conjoint_revenu": 0}
    res = adapter.validate_input(manifest, input_json)
    assert res["ok"]

    out = adapter.execute_sync(manifest, "run1", input_json, exec_opts={"timeout_seconds": 10})
    assert out["status"] == "success", out
    assert out["output"]["nombre_parts"] == 3
    assert abs(out["output"]["valeur"] - 32000 / 3) < 0.01


def test_execute_matches_python_example():
    # Same computation as examples/python/sample_algorithm.py, both should agree.
    from adapters.python_adapter import PythonAdapter

    catala_manifest = json.loads(Path("examples/catala/manifest.json").read_text())
    python_manifest = json.loads(Path("examples/python/manifest.json").read_text())

    catala_out = CatalaAdapter().execute_sync(
        catala_manifest, "run1", {"agent_revenu": 32000, "agent_enfants": 2, "conjoint_revenu": 0},
        exec_opts={"timeout_seconds": 10},
    )
    python_out = PythonAdapter().execute_sync(
        python_manifest, "run2", {"agent_revenu": 32000, "agent_enfants": 2},
        exec_opts={"timeout_seconds": 10},
    )
    assert catala_out["status"] == "success"
    assert python_out["status"] == "success"
    python_value = float(python_out["output"]["value"].rstrip("€"))
    assert abs(catala_out["output"]["valeur"] - python_value) < 0.01


def test_missing_input_field_reports_failure_not_crash():
    adapter = CatalaAdapter()
    manifest = json.loads(Path("examples/catala/manifest.json").read_text())
    res = adapter.validate_input(manifest, {"agent_revenu": 1000})
    assert not res["ok"]
