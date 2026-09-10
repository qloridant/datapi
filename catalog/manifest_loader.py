import json
import tomllib
from pathlib import Path
from typing import Any, Dict

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
    """Load a manifest.json, filling gaps from a sibling pyproject.toml if present."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())

    pyproject_path = manifest_path.parent / "pyproject.toml"
    if pyproject_path.exists():
        manifest = enrich_with_pyproject_text(manifest, pyproject_path.read_text())

    return manifest
