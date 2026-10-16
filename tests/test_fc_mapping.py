import json
from pathlib import Path

from user.fc_mapping import FCMappingEngine, extract_mappings

MANIFEST_PATH = Path("examples/pass-culture-package/manifest.json")


def _load_manifest():
    return json.loads(MANIFEST_PATH.read_text())


def test_extract_mappings_reads_franceconnect_keyword_on_properties():
    manifest = _load_manifest()
    mappings = extract_mappings(manifest["input_schema"])
    assert mappings == {
        "data.date_naissance": "$default.birthdate",
        "data.address": "$default.address",
    }


def test_extract_mappings_skips_properties_without_keyword():
    schema = {
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "properties": {
                    "date_naissance": {"type": "string", "franceconnect": "$default.birthdate"},
                    "departement": {"type": "string"},
                },
            },
            "context": {
                "type": "object",
                "properties": {"date_evaluation": {"type": "string"}},
            },
        },
    }
    assert extract_mappings(schema) == {"data.date_naissance": "$default.birthdate"}


def test_generate_input_payload_prefills_mapped_fields_from_fc_claims():
    engine = FCMappingEngine()
    manifest = _load_manifest()
    claims = {"birthdate": "2007-06-15", "email": "jean@example.fr"}

    payload, missing, consent = engine.generate_input_payload(claims, manifest)

    assert payload["data"]["date_naissance"] == "2007-06-15"
    # claim absente -> pas de prefill, champ remonte comme manquant
    assert "address" not in payload["data"]
    assert "data.address" in [f["path"] for f in missing]


def test_get_field_metadata_covers_data_and_context_with_defaults():
    engine = FCMappingEngine()
    manifest = _load_manifest()
    claims = {"birthdate": "2007-06-15"}

    fields = engine.get_field_metadata(claims, manifest)

    # Tous les champs du schéma remontent, dans l'ordre de déclaration
    assert [f["group"] for f in fields] == ["data", "data", "context", "context"]
    by_path = {f["path"]: f for f in fields}

    # Champ mappé FC : valeur depuis les claims
    data_field = by_path["data.date_naissance"]
    assert data_field["has_fc_value"] is True
    assert data_field["value"] == "2007-06-15"
    assert data_field["label"] == "Date de naissance"

    # Champ de contexte : valeur par défaut du schéma, pas de mapping
    ctx_field = by_path["context.date_evaluation"]
    assert ctx_field["mapping"] is None
    assert ctx_field["has_fc_value"] is False
    assert ctx_field["value"] == "2025-06-16T00:00:00"
    assert ctx_field["default"] == "2025-06-16T00:00:00"

    assert by_path["context.date_decret_v3"]["value"] == "2025-02-27T00:00:00"


def test_get_field_metadata_required_comes_from_parent_schema():
    engine = FCMappingEngine()
    manifest = {
        "input_schema": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "object",
                    "required": ["date_evaluation"],
                    "properties": {
                        "date_evaluation": {"type": "string", "default": "2025-06-16T00:00:00"},
                        "autre": {"type": "string"},
                    },
                }
            },
        }
    }

    fields = engine.get_field_metadata({}, manifest)
    by_path = {f["path"]: f for f in fields}

    assert by_path["context.date_evaluation"]["required"] is True
    assert by_path["context.autre"]["required"] is False


def test_legacy_franceconnect_mapping_block_is_ignored():
    engine = FCMappingEngine()
    manifest = {
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {"age": {"type": "integer", "franceconnect": None}},
                }
            },
        },
        "franceconnect_mapping": {"mappings": {"data.age": "birthdate"}},
    }

    payload, _, _ = engine.generate_input_payload({"birthdate": "1990-01-01"}, manifest)

    # "franceconnect": null => saisie manuelle, l'ancien bloc ne doit plus rien préremplir
    assert payload == {}


def test_validate_mapping_reports_unknown_defaults_per_property():
    engine = FCMappingEngine()
    manifest = {
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "string", "franceconnect": "$default.inconnu"},
                        "y": {"type": "string", "franceconnect": "$default.birthdate"},
                    },
                }
            },
        }
    }

    errors = engine.validate_mapping(manifest)

    assert errors == ["Property 'data.x' references unknown default 'inconnu'"]


def test_server_catalog_flag_detects_mappings_in_input_schema():
    from api.server import extract_mappings as server_extract  # same helper, wired in server

    manifest = _load_manifest()
    assert bool(server_extract(manifest.get("input_schema", {}))) is True

    no_mapping = {"input_schema": {"type": "object", "properties": {"data": {"type": "object"}}}}
    assert bool(server_extract(no_mapping.get("input_schema", {}))) is False
