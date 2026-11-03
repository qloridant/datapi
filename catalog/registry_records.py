import json
import os
import urllib.request
from typing import Any, Dict

REGISTRY_URL = os.environ.get("REGISTRY_URL", "https://datagouv.github.io/regles.data.gouv.fr/registry.json")


def load_registry_records(url: str = REGISTRY_URL) -> Dict[str, Dict[str, Any]]:
    """Read the records published by regles.data.gouv.fr, keyed by record id."""
    with urllib.request.urlopen(url, timeout=10) as response:
        registry = json.load(response)
    return {record["id"]: record for record in registry["records"]}


def describe(manifest: Dict[str, Any], records: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Title, description and organisation of an algorithm, taken from its registry record
    when the manifest names one in `record`, from the manifest otherwise."""
    record = records.get(manifest.get("record", ""))
    if record is None:
        return {
            "title": manifest.get("dct:title", manifest["id"]),
            "description": manifest.get("description", ""),
            "org": manifest.get("org", ""),
            "version": manifest.get("version", ""),
        }
    return {
        "title": record["title"]["fr"],
        "description": record["description"]["fr"],
        "org": record["competent_authority"],
        "version": record["version"],
    }
