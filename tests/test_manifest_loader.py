import json
import tempfile
from pathlib import Path

from catalog.manifest_loader import load_manifest


def test_fills_gaps_from_sibling_pyproject():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "manifest.json").write_text(json.dumps({
            "id": "examples.sample.no_metadata",
            "runtime": {"language": "python", "version": "3.13"},
            "entrypoint": {"type": "python:class", "target": "examples.python.sample_algorithm:SampleQuotientFamilial"},
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        }))
        (tmp / "pyproject.toml").write_text("\n".join([
            "[project]",
            'name = "sample-rules"',
            'version = "1.2.3"',
            'description = "Sample rules package"',
            'license = { text = "MIT" }',
            'keywords = ["sample", "rules"]',
        ]))

        manifest = load_manifest(tmp / "manifest.json")

        assert manifest["name"] == "sample-rules"
        assert manifest["version"] == "1.2.3"
        assert manifest["description"] == "Sample rules package"
        assert manifest["license"] == "MIT"
        assert manifest["tags"] == ["sample", "rules"]


def test_manifest_fields_take_precedence_over_pyproject():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "manifest.json").write_text(json.dumps({
            "id": "examples.sample.explicit_metadata",
            "name": "Manifest Name",
            "runtime": {"language": "python", "version": "3.13"},
            "entrypoint": {"type": "python:class", "target": "examples.python.sample_algorithm:SampleQuotientFamilial"},
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        }))
        (tmp / "pyproject.toml").write_text("\n".join([
            "[project]",
            'name = "pyproject-name"',
            'version = "1.2.3"',
        ]))

        manifest = load_manifest(tmp / "manifest.json")

        assert manifest["name"] == "Manifest Name"
        assert manifest["version"] == "1.2.3"


def test_no_sibling_pyproject_is_a_no_op():
    manifest = load_manifest("examples/python/manifest.json")
    assert manifest["name"] == "Example Quotient Familial (Python)"
