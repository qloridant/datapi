import importlib
import traceback
import time
from typing import Any, Dict
from adapters.adapter_base import AdapterBase
from jsonschema import validate as js_validate, ValidationError

class PythonAdapter(AdapterBase):
    def identify(self):
        return {"name": "python", "version": "0.1.0", "capabilities": {"sync": True, "async": False}}

    def validate_manifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        # minimal checks
        if manifest.get("runtime", {}).get("language") != "python":
            return {"ok": False, "error": "not a python runtime"}
        if "entrypoint" not in manifest:
            return {"ok": False, "error": "missing entrypoint"}
        return {"ok": True}

    def validate_input(self, manifest: Dict[str, Any], input_json: Dict[str, Any]) -> Dict[str, Any]:
        try:
            js_validate(instance=input_json, schema=manifest["input_schema"])
            return {"ok": True}
        except ValidationError as e:
            return {"ok": False, "error": str(e)}

    def prepare(self, manifest: Dict[str, Any], run_id: str, storage: Dict[str, Any]) -> Dict[str, Any]:
        # POC: nothing to prepare for local python module
        return {"ok": True}

    def _load_callable(self, target: str):
        # expected format: package.module:ClassName or package.module:function_name
        if ":" not in target:
            raise RuntimeError("entrypoint.target expected format module:path")
        module_path, attr = target.split(":", 1)
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    def execute_sync(self, manifest: Dict[str, Any], run_id: str, input_json: Dict[str, Any], exec_opts: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        try:
            # validate input
            v = self.validate_input(manifest, input_json)
            if not v.get("ok"):
                return {"status": "failed", "error": v.get("error")}
            entry = manifest["entrypoint"]
            if entry["type"] not in ("python:class", "python:function"):
                return {"status": "failed", "error": "unsupported python entrypoint type"}
            target = entry["target"]
            callable_obj = self._load_callable(target)
            # if class, instantiate and call run(); if function, call directly
            if entry["type"] == "python:class":
                instance = callable_obj()
                out = instance.run(input_json)
            else:
                out = callable_obj(input_json)
            duration = time.time() - start
            return {
                "status": "success",
                "output": out,
                "metrics": {"runtime_seconds": duration},
                "provenance": {"adapter": "python_adapter_v0.1"}
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "trace": traceback.format_exc()}
    def execute_async(self, manifest, run_id, input_json, exec_opts):
        raise NotImplementedError("async not implemented in POC")

    def cancel(self, job_id: str):
        return {"ok": False, "error": "not supported in POC"}

    def cleanup(self, run_id: str):
        return {"ok": True}
