"""Adapter for algorithms implemented in Catala (https://catala-lang.org/).

A Catala program is compiled ahead of time (`catala python` or `clerk build`)
into a Python module that exposes, for each scope, an input structure, an
output structure and a function `scope(input) -> output`. The engine of the
registry, `engine-catala` (https://github.com/datagouv/regles.data.gouv.fr,
folder `engines/catala`), loads that compiled module, converts JSON inputs
and outputs, and infers the input and output schemas of a scope. This adapter
translates between Datapi's manifest and that engine.

Manifest conventions expected by this adapter:
  runtime.language   = "catala"
  entrypoint.type     = "catala:scope"
  entrypoint.target    = "package.module:scope_function_name"

Input types that the engine cannot convert from JSON (enumerations such as
CatalaEnum payloads) raise UnsupportedType; for those, write a small Python
wrapper around the compiled scope and register it with `PythonAdapter`.
"""
import time
import traceback
from typing import Any, Dict

import engine_catala
from adapters.adapter_base import AdapterBase
from jsonschema import validate as js_validate, ValidationError


class CatalaAdapter(AdapterBase):
    def identify(self):
        return {"name": "catala", "version": "0.2.0", "capabilities": {"sync": True, "async": False}}

    def validate_manifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        if manifest.get("runtime", {}).get("language") != "catala":
            return {"ok": False, "error": "not a catala runtime"}
        entry = manifest.get("entrypoint", {})
        if entry.get("type") != "catala:scope":
            return {"ok": False, "error": "entrypoint.type must be 'catala:scope'"}
        target = entry.get("target")
        if not target or ":" not in target:
            return {"ok": False, "error": "entrypoint.target expected format module:scope_function"}
        return {"ok": True}

    def validate_input(self, manifest: Dict[str, Any], input_json: Dict[str, Any]) -> Dict[str, Any]:
        try:
            js_validate(instance=input_json, schema=manifest["input_schema"])
            return {"ok": True}
        except ValidationError as e:
            return {"ok": False, "error": str(e)}

    def prepare(self, manifest: Dict[str, Any], run_id: str, storage: Dict[str, Any]) -> Dict[str, Any]:
        # compilation is a build-time concern: check that the compiled module imports
        try:
            engine_catala.load_scope(manifest["entrypoint"]["target"])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def infer_manifest_schemas(self, target: str) -> Dict[str, Any]:
        contract = engine_catala.infer_call_contract(target)
        return {
            "input_schema": contract["input_schema"],
            "output_schema": contract["output_schema"],
            "sample_inputs": contract["sample_input"],
            "warnings": contract["warnings"],
        }

    def execute_sync(self, manifest: Dict[str, Any], run_id: str, input_json: Dict[str, Any], exec_opts: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        try:
            v = self.validate_input(manifest, input_json)
            if not v.get("ok"):
                return {"status": "failed", "error": v.get("error")}
            target = manifest["entrypoint"]["target"]
            output = engine_catala.execute(target, input_json)
            module, _, scope = target.partition(":")
            return {
                "status": "success",
                "output": output,
                "metrics": {"runtime_seconds": time.time() - start},
                "provenance": {"adapter": "catala_adapter_v0.2", "module": module, "scope": scope},
            }
        except engine_catala.ScopeError as e:
            # the scope's own logic rejected the computation: a business outcome, not an infrastructure error
            return {"status": "failed", "error": f"catala runtime error: {e}"}
        except Exception as e:
            return {"status": "error", "error": str(e), "trace": traceback.format_exc()}

    def execute_async(self, manifest, run_id, input_json, exec_opts):
        raise NotImplementedError("async not implemented in POC")

    def cancel(self, job_id: str):
        return {"ok": False, "error": "not supported in POC"}

    def cleanup(self, run_id: str):
        return {"ok": True}
