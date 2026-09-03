import traceback
from adapters.python_adapter import PythonAdapter

def execute_job(manifest: dict, input_json: dict, run_id: str):
    adapter = PythonAdapter()
    try:
        res = adapter.execute_sync(manifest, run_id, input_json, exec_opts={"timeout_seconds": manifest.get("resources", {}).get("timeout_seconds", 60)})
        return {"status": "finished", "result": res}
    except Exception as e:
        tb = traceback.format_exc()
        return {"status": "error", "error": str(e), "trace": tb}
