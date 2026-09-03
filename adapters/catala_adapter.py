"""Adapter for algorithms implemented in Catala (https://catala-lang.org/).

Catala is a DSL for turning legal/regulatory text into faithful, auditable
executable code. A Catala program (`.catala_fr`/`.catala_en` sources) is
compiled ahead of time -- e.g. with `catala python` or `clerk build` -- into
a plain Python module exposing, for each scope, an input dataclass-like
struct, an output struct, and a function `scope_name(input) -> output`.
This adapter loads that *already compiled* module and drives it, the same
way `PythonAdapter` drives a hand-written Python callable.

This mirrors the pattern used by real Catala deployments such as
Prest'Agri (https://github.com/betagouv/prestagri): compilation happens
offline (`catala`/`clerk`) and is checked in or built as a separate step;
the adapter only ever imports and calls the generated code. See
`examples/catala/` for a worked example, including how it was compiled.

Manifest conventions expected by this adapter:
  runtime.language   = "catala"
  entrypoint.type     = "catala:scope"
  entrypoint.target    = "package.module:scope_function_name"
      (the module produced by the Catala compiler; the function is the
      scope entrypoint, e.g. `quotient_familial`)

Input/output marshalling:
  JSON <-> Catala values is done generically for the primitive types Money,
  Integer, Decimal, Bool, Date, Option and Array/List, plus nested
  CatalaStruct fields, driven by the type hints on the generated input
  struct (obtained via `typing.get_type_hints`, no manual mapping needed).
  Domain-specific types the compiler marks "external" (e.g. CatalaEnum
  payloads) aren't guessed at; for those, write a small Python wrapper
  around the generated scope call (as prestagri's `aides.py`/`utils.py`
  do) and register it with `PythonAdapter` instead -- the two adapters
  compose rather than duplicate each other's job.
"""
import importlib
import inspect
import time
import traceback
import typing
from typing import Any, Dict
from adapters.adapter_base import AdapterBase
from jsonschema import validate as js_validate, ValidationError


class CatalaAdapter(AdapterBase):
    def identify(self):
        return {"name": "catala", "version": "0.1.0", "capabilities": {"sync": True, "async": False}}

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
        # POC: compilation (catala/clerk) is a build-time concern, done ahead
        # of registration -- nothing to do at run time but make sure the
        # generated module actually imports.
        try:
            self._load_scope(manifest["entrypoint"]["target"])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _load_scope(self, target: str):
        module_path, attr = target.split(":", 1)
        mod = importlib.import_module(module_path)
        func = getattr(mod, attr)
        params = list(inspect.signature(func).parameters)
        if len(params) != 1:
            raise RuntimeError(f"catala scope entrypoint '{attr}' must take exactly one input struct argument")
        # generated modules use `from __future__ import annotations`, so raw
        # annotations are unresolved strings; get_type_hints resolves them
        # against the function's own module globals.
        hints = typing.get_type_hints(func)
        input_cls = hints.get(params[0])
        if input_cls is None:
            raise RuntimeError(f"catala scope entrypoint '{attr}' has no type annotation on its input parameter")
        return mod, func, input_cls

    # -- generic JSON <-> catala_runtime value marshalling -----------------

    def _rt(self, mod):
        """Pull the catala_runtime classes out of the generated module's own
        namespace (it does `from .catala_runtime import *`), so we always
        match the exact runtime instance the generated code was built
        against instead of assuming a fixed import path."""
        names = ("Money", "Integer", "Decimal", "Bool", "Date", "Option", "Array", "CatalaStruct", "CatalaEnum", "CatalaError")
        rt = {}
        for name in names:
            if hasattr(mod, name):
                rt[name] = getattr(mod, name)
        return rt

    def _to_catala(self, value: Any, target_type: Any, rt: Dict[str, Any]) -> Any:
        origin = typing.get_origin(target_type)
        args = typing.get_args(target_type)

        if origin is not None and rt.get("Option") is not None and origin is rt["Option"]:
            return rt["Option"](None if value is None else self._to_catala(value, args[0], rt))
        if origin is not None and rt.get("Array") is not None and origin is rt["Array"]:
            if not isinstance(value, list):
                raise ValueError(f"expected a list, got {type(value).__name__}")
            return rt["Array"]([self._to_catala(item, args[0], rt) for item in value])

        if isinstance(target_type, type) and rt.get("CatalaStruct") and issubclass(target_type, rt["CatalaStruct"]):
            if not isinstance(value, dict):
                raise ValueError(f"expected an object for struct {target_type.__name__}, got {type(value).__name__}")
            hints = typing.get_type_hints(target_type)
            field_hints = {k: v for k, v in hints.items() if k in target_type.fields}
            kwargs = {}
            missing = []
            for field, field_type in field_hints.items():
                # scope *input* structs get an auto-generated `_in` suffix
                # on every field (e.g. `agent_revenu` -> `agent_revenu_in`);
                # accept the JSON key with or without it.
                json_key = field if field in value else field.removesuffix("_in")
                if json_key not in value:
                    missing.append(field)
                    continue
                kwargs[field] = self._to_catala(value[json_key], field_type, rt)
            if missing:
                raise ValueError(f"missing field(s) {sorted(missing)} for struct {target_type.__name__}")
            return target_type(**kwargs)

        if target_type is rt.get("Money") or target_type is rt.get("Decimal"):
            # constructed from a string to avoid binary-float rounding noise
            return target_type(str(value))
        if target_type is rt.get("Integer"):
            return target_type(int(value))
        if target_type is rt.get("Bool"):
            return target_type(bool(value))
        if target_type is rt.get("Date"):
            y, m, d = str(value).split("-")
            return target_type((int(y), int(m), int(d)))

        raise ValueError(f"unsupported catala input type '{getattr(target_type, '__name__', target_type)}'; "
                          f"write a Python wrapper (PythonAdapter) for this field instead")

    def _from_catala(self, value: Any, rt: Dict[str, Any]) -> Any:
        if rt.get("Option") is not None and isinstance(value, rt["Option"]):
            return None if value.value is None else self._from_catala(value.value, rt)
        if rt.get("Array") is not None and isinstance(value, rt["Array"]):
            return [self._from_catala(item, rt) for item in value]
        if rt.get("CatalaStruct") is not None and isinstance(value, rt["CatalaStruct"]):
            return {field: self._from_catala(getattr(value, field), rt) for field in value.fields}
        if rt.get("CatalaEnum") is not None and isinstance(value, rt["CatalaEnum"]):
            return {"code": value.code.name, "payload": self._from_catala(value.payload, rt)}
        if rt.get("Money") is not None and isinstance(value, rt["Money"]):
            return float(value)
        if rt.get("Decimal") is not None and isinstance(value, rt["Decimal"]):
            return float(value)
        if rt.get("Integer") is not None and isinstance(value, rt["Integer"]):
            return int(value)
        if rt.get("Bool") is not None and isinstance(value, rt["Bool"]):
            return bool(value)
        if rt.get("Date") is not None and isinstance(value, rt["Date"]):
            d = value.value
            return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
        # already a plain python value (or an unsupported Catala type we
        # just pass through best-effort via str())
        if isinstance(value, (str, int, float, bool, type(None), list, dict)):
            return value
        return str(value)

    def execute_sync(self, manifest: Dict[str, Any], run_id: str, input_json: Dict[str, Any], exec_opts: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        try:
            v = self.validate_input(manifest, input_json)
            if not v.get("ok"):
                return {"status": "failed", "error": v.get("error")}

            target = manifest["entrypoint"]["target"]
            mod, func, input_cls = self._load_scope(target)
            rt = self._rt(mod)

            catala_input = self._to_catala(input_json, input_cls, rt)
            catala_output = func(catala_input)
            output = self._from_catala(catala_output, rt)

            duration = time.time() - start
            return {
                "status": "success",
                "output": output,
                "metrics": {"runtime_seconds": duration},
                "provenance": {"adapter": "catala_adapter_v0.1", "module": mod.__name__, "scope": func.__name__},
            }
        except Exception as e:
            # A CatalaError (NoValue, DivisionByZero, AssertionFailed, ...)
            # means the scope's own logic rejected the computation -- that's
            # a "failed" business outcome, not an adapter/infra "error".
            catala_error = None
            if "rt" in locals():
                catala_error = rt.get("CatalaError")
            if catala_error is not None and isinstance(e, catala_error):
                return {"status": "failed", "error": f"catala runtime error: {e}"}
            return {"status": "error", "error": str(e), "trace": traceback.format_exc()}

    def execute_async(self, manifest, run_id, input_json, exec_opts):
        raise NotImplementedError("async not implemented in POC")

    def cancel(self, job_id: str):
        return {"ok": False, "error": "not supported in POC"}

    def cleanup(self, run_id: str):
        return {"ok": True}
