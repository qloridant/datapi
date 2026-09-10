import json
from adapters.catala_adapter import CatalaAdapter
from catalog.manifest_loader import load_manifests
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


def test_infer_manifest_schemas_matches_hand_written_manifest():
    # the generated schemas should be usable as drop-in replacements for the
    # hand-written ones in examples/catala/manifest.json
    manifest = json.loads(Path("examples/catala/manifest.json").read_text())
    target = manifest["entrypoint"]["target"]
    inferred = CatalaAdapter().infer_manifest_schemas(target)
    assert inferred["warnings"] == []
    assert set(inferred["input_schema"]["required"]) == set(manifest["input_schema"]["required"])
    assert set(inferred["output_schema"]["required"]) == set(manifest["output_schema"]["required"])

    manifest["input_schema"] = inferred["input_schema"]
    manifest["output_schema"] = inferred["output_schema"]
    out = CatalaAdapter().execute_sync(
        manifest, "run1", {"agent_revenu": 32000, "agent_enfants": 2, "conjoint_revenu": 0},
        exec_opts={"timeout_seconds": 10},
    )
    assert out["status"] == "success", out

    # sample_inputs should itself be a valid, runnable input for the same scope.
    assert set(inferred["sample_inputs"]) == set(manifest["input_schema"]["required"])
    out = CatalaAdapter().execute_sync(manifest, "run2", inferred["sample_inputs"], exec_opts={"timeout_seconds": 10})
    assert out["status"] == "success", out


def test_infer_manifest_schemas_handles_nested_structs_and_enums():
    # examples/prestagri: nested CatalaStruct, List[CatalaStruct] and, in the
    # output, a List[CatalaEnum] field (criteres_applicables) -- none of which
    # examples/catala exercises. examples/prestagri/manifest.json is a package
    # manifest (see catalog/manifest.schema.json's algorithms form); flatten it
    # to get at the single aide-scolarite algorithm entry.
    manifest = load_manifests("examples/prestagri/manifest.json")[0]
    target = manifest["entrypoint"]["target"]
    inferred = CatalaAdapter().infer_manifest_schemas(target)
    assert inferred["warnings"] == []

    foyer = inferred["input_schema"]["properties"]["foyer_fiscal_agent"]
    assert foyer["type"] == "object"
    assert "membres_du_foyer" in foyer["required"]
    membre_item = foyer["properties"]["membres_du_foyer"]["items"]
    assert set(membre_item["required"]) == {"revenu_fiscal_reference", "nombre_personnes"}

    criteres_item = inferred["output_schema"]["properties"]["criteres_applicables"]["items"]
    assert set(criteres_item["required"]) == {"code", "payload"}

    manifest["input_schema"] = inferred["input_schema"]
    manifest["output_schema"] = inferred["output_schema"]
    out = CatalaAdapter().execute_sync(manifest, "run1", manifest["sample_inputs"], exec_opts={"timeout_seconds": 10})
    assert out["status"] == "success", out

    # generated sample_inputs: options unwrapped to a real sample (not null), nested
    # struct/array fields populated the same way, and it should itself execute cleanly.
    trajet = inferred["sample_inputs"]["trajet_depuis_domicile_agent"]
    assert trajet == {"distance_km": 1, "duree_minutes": 1}
    membre = inferred["sample_inputs"]["foyer_fiscal_agent"]["membres_du_foyer"][0]
    assert set(membre) == {"revenu_fiscal_reference", "nombre_personnes"}
    out = CatalaAdapter().execute_sync(manifest, "run2", inferred["sample_inputs"], exec_opts={"timeout_seconds": 10})
    assert out["status"] == "success", out
