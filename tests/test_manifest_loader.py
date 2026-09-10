import json
import tempfile
from pathlib import Path

from catalog.manifest_loader import load_manifest, load_manifests


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


def _algorithm_entry(id_, **overrides):
    entry = {
        "id": id_,
        "name": f"Algo {id_}",
        "runtime": {"language": "python", "version": "3.13"},
        "entrypoint": {"type": "python:function", "target": "mod:fn"},
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
    }
    entry.update(overrides)
    return entry


def test_load_manifests_single_algorithm_is_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "manifest.json").write_text(json.dumps(_algorithm_entry("examples.sample.one")))

        entries = load_manifests(tmp / "manifest.json")

        assert entries == [load_manifest(tmp / "manifest.json")]


def test_load_manifests_package_merges_shared_fields_with_algorithm_precedence():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        package = {
            "org": "shared.org",
            "license": "MIT",
            "tags": ["shared"],
            "dct:source": {"schema:codeRepository": "https://example.org/repo"},
            "algorithms": [
                _algorithm_entry("pkg.algo_a"),
                _algorithm_entry("pkg.algo_b", org="own.org"),
            ],
        }
        (tmp / "manifest.json").write_text(json.dumps(package))

        entries = load_manifests(tmp / "manifest.json")

        assert [e["id"] for e in entries] == ["pkg.algo_a", "pkg.algo_b"]
        assert entries[0]["org"] == "shared.org"
        assert entries[0]["license"] == "MIT"
        assert entries[0]["tags"] == ["shared"]
        assert entries[0]["metadata_raw"]["dct:source"] == {"schema:codeRepository": "https://example.org/repo"}
        # algorithm already set its own org -> package's org must not overwrite it
        assert entries[1]["org"] == "own.org"


def test_load_manifest_on_package_file_raises_explicit_error():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "manifest.json").write_text(json.dumps({"algorithms": [_algorithm_entry("pkg.algo_a")]}))

        try:
            load_manifest(tmp / "manifest.json")
            assert False, "expected ValueError"
        except ValueError as e:
            assert "load_manifests" in str(e)
