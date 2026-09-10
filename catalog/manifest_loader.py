import json
import tomllib
from pathlib import Path
from typing import Any, Dict, List

# Manifest fields that can be filled in from the sibling pyproject.toml's
# [project] table when the manifest omits them. The manifest wins whenever
# it sets a field itself; pyproject.toml only covers the gaps.
_FALLBACK_FIELDS = ("name", "version", "description")


def _project_license(project: Dict[str, Any]) -> str | None:
    license_ = project.get("license")
    if isinstance(license_, str):
        return license_
    if isinstance(license_, dict):
        return license_.get("text")
    return None


def enrich_with_pyproject_text(manifest: Dict[str, Any], pyproject_text: str) -> Dict[str, Any]:
    """Fill manifest metadata gaps from a pyproject.toml's [project] table (as raw text)."""
    project = tomllib.loads(pyproject_text).get("project", {})

    for field in _FALLBACK_FIELDS:
        if field not in manifest and field in project:
            manifest[field] = project[field]

    if "license" not in manifest:
        license_ = _project_license(project)
        if license_ is not None:
            manifest["license"] = license_

    if "tags" not in manifest and project.get("keywords"):
        manifest["tags"] = project["keywords"]

    return manifest


def load_manifest(manifest_path: str | Path) -> Dict[str, Any]:
    """Load a single-algorithm manifest.json, filling gaps from a sibling
    pyproject.toml if present. Raises ValueError if the file is a package
    manifest (has an "algorithms" array) -- use load_manifests for those."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())

    if "algorithms" in manifest:
        raise ValueError(
            f"{manifest_path} is a package manifest (has 'algorithms') -- use load_manifests(...) instead"
        )

    pyproject_path = manifest_path.parent / "pyproject.toml"
    if pyproject_path.exists():
        manifest = enrich_with_pyproject_text(manifest, pyproject_path.read_text())

    return manifest


# Package-level fields gap-filled directly onto each flattened algorithm entry
# (never overwriting a field the algorithm entry already sets).
_PACKAGE_DIRECT_FIELDS = ("org", "license", "tags")


def flatten_package_manifest(package: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten a package manifest's "algorithms" into standalone entries,
    gap-filling each with the package's shared fields. `dct:source` at
    package level has a different shape than at algorithm level (see
    catalog/manifest.schema.json) so it is not merged in directly -- it is
    gap-filled under the entry's metadata_raw instead."""
    entries = []
    for algorithm in package["algorithms"]:
        entry = dict(algorithm)
        for field in _PACKAGE_DIRECT_FIELDS:
            if field not in entry and field in package:
                entry[field] = package[field]
        if "dct:source" in package:
            metadata_raw = dict(entry.get("metadata_raw", {}))
            metadata_raw.setdefault("dct:source", package["dct:source"])
            entry["metadata_raw"] = metadata_raw
        entries.append(entry)
    return entries


def load_manifests(manifest_path: str | Path) -> List[Dict[str, Any]]:
    """Load a manifest.json (single-algorithm or package shape), filling gaps
    from a sibling pyproject.toml if present, and return the flattened list
    of algorithm entries (a single-algorithm file yields a one-element list)."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())

    pyproject_path = manifest_path.parent / "pyproject.toml"
    if pyproject_path.exists():
        manifest = enrich_with_pyproject_text(manifest, pyproject_path.read_text())

    if "algorithms" not in manifest:
        return [manifest]
    return flatten_package_manifest(manifest)
