import json
from pathlib import Path

from catalog.registry_records import describe, load_registry_records

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = json.loads((Path(__file__).parent.parent / "examples/civique-droit-vote/manifest.json").read_text())


def records():
    return load_registry_records((FIXTURES / "registry.json").as_uri())


def test_describes_an_algorithm_from_its_registry_record():
    assert describe(MANIFEST, records()) == {
        "title": "Droit de vote en France",
        "description": records()[MANIFEST["record"]]["description"]["fr"],
        "org": "https://github.com/qloridant/regalgo-civique-droit-vote#organisation",
        "version": "1.0.0",
    }


def test_describes_an_algorithm_without_record_from_its_manifest():
    manifest = {"id": "examples.sample.quotient_familial", "dct:title": "Example Quotient Familial (Python)"}
    assert describe(manifest, records())["title"] == "Example Quotient Familial (Python)"
