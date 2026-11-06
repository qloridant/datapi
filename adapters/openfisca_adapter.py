"""Adapter for rules written with OpenFisca (https://openfisca.org/).

The engine of the registry, `engine-openfisca` (https://github.com/datagouv/regles.data.gouv.fr,
folder `engines/openfisca`), reads the variables of the tax and benefit system, infers the input
and output schemas of a rule, and computes it for one person. This adapter translates between
Datapi's manifest and that engine. The country package, such as `openfisca-france`, is a
dependency of Datapi.

Manifest conventions expected by this adapter:
  runtime.language   = "openfisca"
  entrypoint.type     = "openfisca:variables"
  entrypoint.target    = the module of the system, such as "openfisca_france"
  entrypoint.outputs   = the computed variables, such as ["pass_culture"]
  entrypoint.inputs    = the variables read from the inputs, such as ["date_naissance"]
  entrypoint.rolling_year_inputs = optional, the inputs that receive the total of the twelve months
                                   before the month of the calculation, such as ["salaire_imposable"]
"""
import time
import traceback
from typing import Any, Dict

import engine_openfisca
from adapters.adapter_base import AdapterBase
from jsonschema import validate as js_validate, ValidationError


def openfisca_rule(entrypoint: Dict[str, Any]) -> engine_openfisca.OpenfiscaRule:
    return engine_openfisca.OpenfiscaRule(
        system=entrypoint["target"],
        outputs=tuple(entrypoint.get("outputs", [])),
        inputs=tuple(entrypoint.get("inputs", [])),
        rolling_year_inputs=tuple(entrypoint.get("rolling_year_inputs", [])),
    )


class OpenfiscaAdapter(AdapterBase):
    def identify(self):
        return {"name": "openfisca", "version": "0.1.0", "capabilities": {"sync": True, "async": False}}

    def validate_manifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        if manifest.get("runtime", {}).get("language") != "openfisca":
            return {"ok": False, "error": "not an openfisca runtime"}
        entry = manifest.get("entrypoint", {})
        if entry.get("type") != "openfisca:variables":
            return {"ok": False, "error": "entrypoint.type must be 'openfisca:variables'"}
        if not entry.get("target") or not entry.get("outputs"):
            return {"ok": False, "error": "entrypoint.target and entrypoint.outputs required"}
        return {"ok": True}

    def validate_input(self, manifest: Dict[str, Any], input_json: Dict[str, Any]) -> Dict[str, Any]:
        try:
            js_validate(instance=input_json, schema=manifest["input_schema"])
            return {"ok": True}
        except ValidationError as e:
            return {"ok": False, "error": str(e)}

    def prepare(self, manifest: Dict[str, Any], run_id: str, storage: Dict[str, Any]) -> Dict[str, Any]:
        try:
            engine_openfisca.infer_call_contract(openfisca_rule(manifest["entrypoint"]))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def infer_manifest_schemas(self, entrypoint: Dict[str, Any]) -> Dict[str, Any]:
        contract = engine_openfisca.infer_call_contract(openfisca_rule(entrypoint))
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
            entrypoint = manifest["entrypoint"]
            output = engine_openfisca.execute(openfisca_rule(entrypoint), input_json)
            return {
                "status": "success",
                "output": output,
                "metrics": {"runtime_seconds": time.time() - start},
                "provenance": {"adapter": "openfisca_adapter_v0.1", "system": entrypoint["target"], "outputs": entrypoint["outputs"]},
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "trace": traceback.format_exc()}

    def execute_async(self, manifest, run_id, input_json, exec_opts):
        raise NotImplementedError("async not implemented in POC")

    def cancel(self, job_id: str):
        return {"ok": False, "error": "not supported in POC"}

    def cleanup(self, run_id: str):
        return {"ok": True}
