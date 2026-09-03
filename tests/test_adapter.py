import json
from adapters.python_adapter import PythonAdapter
from pathlib import Path

def test_validate_input_and_execute():
    adapter = PythonAdapter()
    manifest_path = Path("examples/python/manifest.json")
    manifest = json.loads(manifest_path.read_text())
    res = adapter.validate_input(manifest, {"agent_revenu": 32000, "agent_enfants": 2})
    assert res["ok"]
    out = adapter.execute_sync(manifest, "run1", {"agent_revenu": 32000, "agent_enfants": 2}, exec_opts={"timeout_seconds": 10})
    assert out["status"] in ("success",)
    assert "output" in out
    assert "value" in out["output"]
