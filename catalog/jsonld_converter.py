"""Pragmatic read/write of the CPSV-AP @context observed in the real
Prest'Agri metadata.jsonld -- not a generic JSON-LD engine. It only knows
about the handful of predicates a Datapi manifest can model (dct:identifier,
cv:hasChannel, dct:source, cv:hasInput/cpsv:produces derived from JSON
Schema), and leaves everything else in metadata_raw for manual review.

The real file's @context aliases short terms to full predicates ("id" for
"@id", "type" for "@type", "title"/"description" for dct:title/dct:description
with an implicit @language) -- per JSON-LD semantics an aliased term and its
full-IRI form are the same predicate, so every helper below that reads a node
accepts either spelling. It also mixes plain string literals with explicit
{"@value": ..., "@language": ...} objects and {"id": "..."}-style references
for the exact same predicate in different nodes -- `_scalar` normalizes both
down to a plain Python value.
"""

import json
from typing import Any, Dict, List, Tuple

# Same prefixes as the real metadata.jsonld's @context.
_JSONLD_CONTEXT = {
    "cpsv": "http://purl.org/vocab/cpsv#",
    "cv": "http://data.europa.eu/m8g/",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "schema": "http://schema.org/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "cprmv": "https://regels.overheid.nl/def/cprmv#",
    "px": "https://github.com/betagouv/prestagri#vocab/",
}

_SOFTWARE_SOURCE_CODE_FIELDS = {
    "schema:codeRepository",
    "schema:programmingLanguage",
    "schema:softwareVersion",
}

_JSON_TYPE_TO_XSD = {
    "string": "xsd:string",
    "integer": "xsd:integer",
    "number": "xsd:decimal",
    "boolean": "xsd:boolean",
}


def _as_package(manifest: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Normalize `manifest` to package shape. Returns (package, was_single)."""
    if "algorithms" in manifest:
        return json.loads(json.dumps(manifest)), False
    return {"algorithms": [json.loads(json.dumps(manifest))]}, True


def _from_package(package: Dict[str, Any], was_single: bool) -> Dict[str, Any]:
    if was_single:
        return package["algorithms"][0]
    return package


def _node_id(node: Any) -> str | None:
    """The node's identifier, whether expressed as "@id" or the aliased "id"."""
    if isinstance(node, dict):
        return node.get("@id", node.get("id"))
    if isinstance(node, str):
        return node
    return None


def _resolve(node: Any, graph_by_id: Dict[str, Any]) -> Any:
    """Resolve a {"id"/"@id": ...} reference (or bare id string) against the @graph index."""
    ref_id = _node_id(node)
    if ref_id is not None and ref_id in graph_by_id:
        return graph_by_id[ref_id]
    return node


def _scalar(value: Any) -> Any:
    """Normalize a JSON-LD value down to a plain Python scalar: unwrap a
    {"@value": ...} language-tagged literal or a {"id"/"@id": ...} reference;
    pass through anything already plain."""
    if isinstance(value, dict):
        if "@value" in value:
            return value["@value"]
        node_id = _node_id(value)
        if node_id is not None:
            return node_id
    return value


def _type_list(node: Dict[str, Any]) -> List[str]:
    t = node.get("@type", node.get("type", []))
    return t if isinstance(t, list) else [t]


def _is_public_service(node: Any) -> bool:
    return isinstance(node, dict) and "cpsv:PublicService" in _type_list(node)


def import_jsonld_into_manifest(manifest: Dict[str, Any], jsonld_text: str) -> Tuple[Dict[str, Any], List[str]]:
    """Gap-fill `manifest` (single-algorithm or package shape) from a CPSV-AP
    metadata.jsonld. Never overwrites a field the manifest already sets.
    Returns (enriched manifest, in the same shape it was given; warnings).
    """
    warnings: List[str] = []
    doc = json.loads(jsonld_text)
    graph = doc.get("@graph", [doc])
    graph_by_id = {
        _node_id(node): node for node in graph if isinstance(node, dict) and _node_id(node) is not None
    }

    candidates = {
        _node_id(node): node
        for node in graph
        if _is_public_service(node) and "dct:hasPart" not in node
    }

    package, was_single = _as_package(manifest)
    algorithms = package["algorithms"]

    matches: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    unmatched_entries: List[Dict[str, Any]] = []

    for entry in algorithms:
        identifier = entry.get("dct:identifier")
        if identifier is None:
            unmatched_entries.append(entry)
            continue
        matched_id = next(
            (cid for cid, node in candidates.items() if node.get("dct:identifier") == identifier),
            None,
        )
        if matched_id is not None:
            matches.append((entry, candidates.pop(matched_id)))

    if unmatched_entries and candidates:
        if len(unmatched_entries) == 1 and len(candidates) == 1:
            entry = unmatched_entries[0]
            _, node = candidates.popitem()
            matches.append((entry, node))
        else:
            raise ValueError(
                f"ambiguous match: {len(unmatched_entries)} algorithm entr{'y' if len(unmatched_entries) == 1 else 'ies'} "
                f"without dct:identifier and {len(candidates)} unmatched service(s) in metadata.jsonld "
                "-- set dct:identifier on each algorithm entry to disambiguate"
            )

    for cid, node in candidates.items():
        warnings.append(
            f"service '{node.get('dct:identifier', cid)}' present in metadata.jsonld but no matching "
            "algorithm entry (set its dct:identifier to match)"
        )

    for entry, node in matches:
        title = node.get("dct:title", node.get("title"))
        if "name" not in entry and title is not None:
            entry["name"] = _scalar(title)
        description = node.get("dct:description", node.get("description"))
        if "description" not in entry and description is not None:
            entry["description"] = _scalar(description)
        entry.setdefault("dct:identifier", node.get("dct:identifier"))

        if "cv:hasChannel" not in entry and node.get("cv:hasChannel") is not None:
            channel = _resolve(node["cv:hasChannel"], graph_by_id)
            if isinstance(channel, dict):
                hc = {}
                if channel.get("foaf:page") is not None:
                    hc["foaf:page"] = _scalar(channel["foaf:page"])
                if channel.get("dct:description") is not None:
                    hc["dct:description"] = _scalar(channel["dct:description"])
                if hc:
                    entry["cv:hasChannel"] = hc

        if "dct:source" not in entry and node.get("dct:source") is not None:
            sources = node["dct:source"]
            sources = sources if isinstance(sources, list) else [sources]
            entry["dct:source"] = [{"id": _node_id(s) or s} for s in sources]

        field_titles: Dict[str, Dict[str, Any]] = {}
        for jsonld_key, schema_key in (("cv:hasInput", "input_schema"), ("cpsv:produces", "output_schema")):
            items = node.get(jsonld_key, [])
            items = items if isinstance(items, list) else [items]
            for item in items:
                item = _resolve(item, graph_by_id)
                if not isinstance(item, dict):
                    continue
                fid = item.get("dct:identifier")
                if not fid:
                    continue
                info = {}
                if item.get("dct:title") is not None:
                    info["title"] = _scalar(item["dct:title"])
                if item.get("cprmv:definition") is not None:
                    info["description"] = _scalar(item["cprmv:definition"])
                field_titles[fid] = info
            schema = entry.get(schema_key)
            if isinstance(schema, dict):
                _fill_schema_titles(schema, field_titles)

    # Package-level dct:source: modeled schema:SoftwareSourceCode fields fill
    # the package's own dct:source (gap-fill); anything else falls through to
    # the package's metadata_raw. The SoftwareSourceCode node is found via the
    # aggregator's own dct:source reference, falling back to a graph-wide scan
    # by @type for single-service metadata.jsonld without an aggregator node.
    aggregator_node = next((n for n in graph if isinstance(n, dict) and "dct:hasPart" in n), None)
    source_code_node = None
    if aggregator_node is not None and aggregator_node.get("dct:source") is not None:
        source_code_node = _resolve(aggregator_node["dct:source"], graph_by_id)
    if not isinstance(source_code_node, dict):
        source_code_node = next(
            (n for n in graph if isinstance(n, dict) and "schema:SoftwareSourceCode" in _type_list(n)), None
        )

    if isinstance(source_code_node, dict):
        if "dct:source" not in package:
            modeled = {k: v for k, v in source_code_node.items() if k in _SOFTWARE_SOURCE_CODE_FIELDS}
            if modeled:
                package["dct:source"] = modeled
        leftover = {
            k: v
            for k, v in source_code_node.items()
            if k not in _SOFTWARE_SOURCE_CODE_FIELDS and k not in ("@id", "@type", "id", "type")
        }
        if leftover:
            package.setdefault("metadata_raw", {}).update(
                {k: v for k, v in leftover.items() if k not in package.get("metadata_raw", {})}
            )

    return _from_package(package, was_single), warnings


def _fill_schema_titles(schema: Dict[str, Any], field_titles: Dict[str, Dict[str, Any]], _seen=None) -> None:
    """Recurse through properties/items at any depth, setting title/description
    (setdefault -- never overwriting) on any property whose name matches a
    known field identifier."""
    _seen = _seen if _seen is not None else set()
    schema_id = id(schema)
    if schema_id in _seen:
        return
    _seen.add(schema_id)

    props = schema.get("properties")
    if isinstance(props, dict):
        for name, sub in props.items():
            if not isinstance(sub, dict):
                continue
            info = field_titles.get(name)
            if info:
                if "title" in info:
                    sub.setdefault("title", info["title"])
                if "description" in info:
                    sub.setdefault("description", info["description"])
            _fill_schema_titles(sub, field_titles, _seen)

    items = schema.get("items")
    if isinstance(items, dict):
        _fill_schema_titles(items, field_titles, _seen)


def _iter_leaf_properties(schema: Dict[str, Any], _seen=None):
    """Yield (name, property_schema, required) for every leaf property, at any
    depth, name-keyed like `_fill_schema_titles` (not path-keyed)."""
    _seen = _seen if _seen is not None else set()
    schema_id = id(schema)
    if schema_id in _seen:
        return
    _seen.add(schema_id)

    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    required = set(schema.get("required") or [])
    for name, sub in props.items():
        if not isinstance(sub, dict):
            continue
        nested = sub.get("properties")
        items = sub.get("items")
        if isinstance(nested, dict):
            yield from _iter_leaf_properties(sub, _seen)
        elif isinstance(items, dict) and isinstance(items.get("properties"), dict):
            yield from _iter_leaf_properties(items, _seen)
        else:
            yield name, sub, name in required


def _xsd_type(prop_schema: Dict[str, Any]) -> str:
    t = prop_schema.get("type", "string")
    types = t if isinstance(t, list) else [t]
    for candidate in types:
        if candidate != "null" and candidate in _JSON_TYPE_TO_XSD:
            return _JSON_TYPE_TO_XSD[candidate]
    return "xsd:string"


def _flatten_to_field_nodes(schema: Any) -> List[Dict[str, Any]]:
    if not isinstance(schema, dict):
        return []
    nodes = []
    for name, prop_schema, required in _iter_leaf_properties(schema):
        node: Dict[str, Any] = {
            "dct:identifier": name,
            "cprmv:type": _xsd_type(prop_schema),
            "schema:valueRequired": required,
        }
        if prop_schema.get("title") is not None:
            node["dct:title"] = prop_schema["title"]
        if prop_schema.get("description") is not None:
            node["cprmv:definition"] = prop_schema["description"]
        nodes.append(node)
    return nodes


def _algorithm_to_service_node(algorithm: Dict[str, Any]) -> Dict[str, Any]:
    identifier = algorithm.get("dct:identifier", algorithm["id"])
    node: Dict[str, Any] = {
        "@id": identifier,
        "@type": "cpsv:PublicService",
        "dct:identifier": identifier,
        "dct:title": algorithm.get("name"),
        "dct:description": algorithm.get("description"),
        "cv:hasInput": _flatten_to_field_nodes(algorithm.get("input_schema")),
        "cpsv:produces": _flatten_to_field_nodes(algorithm.get("output_schema")),
    }
    if algorithm.get("cv:hasChannel") is not None:
        node["cv:hasChannel"] = algorithm["cv:hasChannel"]
    if algorithm.get("dct:source") is not None:
        node["dct:source"] = algorithm["dct:source"]
    return node


def manifest_to_jsonld(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a CPSV-AP metadata.jsonld from a manifest (single-algorithm or
    package shape). Inverse of `import_jsonld_into_manifest` for the fields it
    models -- not a generic JSON-LD engine."""
    package, was_single = _as_package(manifest)
    algorithms = package["algorithms"]

    service_nodes = [_algorithm_to_service_node(a) for a in algorithms]
    graph = list(service_nodes)

    if not was_single and len(algorithms) >= 2:
        aggregator_id = package.get("org", "package")
        aggregator: Dict[str, Any] = {
            "@id": aggregator_id,
            "@type": "cpsv:PublicService",
            "dct:hasPart": [{"@id": node["@id"]} for node in service_nodes],
        }
        package_source = package.get("dct:source")
        if isinstance(package_source, dict):
            source_id = f"{aggregator_id}#software-source-code"
            aggregator["dct:source"] = {"@id": source_id}
            graph.append({"@id": source_id, "@type": "schema:SoftwareSourceCode", **package_source})
        graph = [aggregator] + graph

    return {"@context": _JSONLD_CONTEXT, "@graph": graph}
