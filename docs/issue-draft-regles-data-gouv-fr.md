# Draft issue for datagouv/regles.data.gouv.fr

**Not opened yet** — for review before posting. Title suggestion below.

---

**Title:** Accept a unified Datapi-style manifest (single or multi-algorithm) as an alternative to a hand-written metadata.jsonld

## Context

[Datapi](https://github.com/<org>/datapi) registers algorithms via a
`manifest.json` (`entrypoint`, `input_schema`/`output_schema`, etc.). To also
register on regles.data.gouv.fr, teams currently write a second file by
hand: `metadata.jsonld`, in CPSV-AP.

[Prest'Agri](https://github.com/betagouv/prestagri)'s real `metadata.jsonld`
shows the natural shape for a repo exposing more than one service: a single
file, one `cpsv:PublicService` aggregator with `dct:hasPart` grouping several
services (here: `quotient-familial` and `aide-scolarite`). Datapi's
`manifest.json`, by contrast, historically described exactly one algorithm
per file.

We extended Datapi's manifest format to support both cardinalities natively
(`catalog/manifest.schema.json`, `catalog/jsonld_converter.py`) and to use
CPSV-AP vocabulary directly (`dct:identifier`, `cv:hasChannel`, `dct:source`)
instead of inventing Datapi-only field names that would need translating.
This issue proposes regles.data.gouv.fr accept that same manifest as an
ingestion input, so a repo maintains one file instead of two.

## Worked example: examples/prestagri/

[`examples/prestagri/manifest.json`](../examples/prestagri/manifest.json) is
Prest'Agri's real `metadata.jsonld`, migrated once via
`catalog.jsonld_converter.import_jsonld_into_manifest` and re-shaped into a
Datapi package manifest (shared `org`/`dct:source` at the top, one entry per
algorithm under `algorithms`):

```json
{
  "org": "betagouv.prestagri",
  "dct:source": {
    "schema:codeRepository": "https://github.com/betagouv/prestagri/tree/478b3cc2ab28299c73b94fdd192b0559ae5873b8",
    "schema:programmingLanguage": ["Python", "Catala"],
    "schema:softwareVersion": "0.1.0"
  },
  "algorithms": [
    {
      "id": "examples.sample.aide_scolarite_prestagri",
      "dct:identifier": "prestagri-aide-scolarite",
      "name": "Aide à la scolarité (Prest'Agri)",
      "cv:hasChannel": {
        "foaf:page": "https://api.prest-agri.beta.gouv.fr/aide_scolarite",
        "dct:description": "Point d'accès HTTP GET, réponses JSON."
      },
      "dct:source": [
        { "id": "https://github.com/betagouv/prestagri/blob/.../aide_scolarite.catala_fr#CalculAideScolarite" }
      ],
      "runtime": { "...": "..." },
      "entrypoint": { "...": "..." },
      "input_schema": { "...": "..." },
      "output_schema": { "...": "..." }
    }
  ]
}
```

(Only `aide-scolarite` is registered as a Datapi algorithm today;
`quotient-familial` is not yet vendored, so the migration script correctly
left it out rather than fabricating an `entrypoint` for it — it surfaced as
a warning instead: `service 'prestagri-quotient-familial' present in
metadata.jsonld but no matching algorithm entry`.)

`catalog.jsonld_converter.manifest_to_jsonld` derives a `metadata.jsonld`
back from that same manifest (exposed as `GET
/catalog/{id}/metadata.jsonld`):

```json
{
  "@id": "prestagri-aide-scolarite",
  "@type": "cpsv:PublicService",
  "dct:identifier": "prestagri-aide-scolarite",
  "dct:title": "Aide à la scolarité (Prest'Agri)",
  "cv:hasChannel": {
    "foaf:page": "https://api.prest-agri.beta.gouv.fr/aide_scolarite",
    "dct:description": "Point d'accès HTTP GET, réponses JSON."
  },
  "dct:source": [
    { "id": "https://github.com/betagouv/prestagri/blob/.../aide_scolarite.catala_fr#CalculAideScolarite" }
  ],
  "cv:hasInput": [ "...derived from input_schema..." ],
  "cpsv:produces": [ "...derived from output_schema..." ]
}
```

`dct:identifier`/`dct:title`/`cv:hasChannel`/`dct:source` round-trip exactly
against the original file's `service-aide-scolarite` node.
`cv:hasInput`/`cpsv:produces` are freshly derived from `input_schema`/
`output_schema` and don't match the original hand-written parameter list
1:1 in this case — Prest'Agri's public HTTP API takes higher-level inputs
(`agent_revenu`, `adresse_agent`, ...) than the raw Catala scope vendored
into Datapi (`foyer_fiscal_agent`, `trajet_depuis_domicile_agent`, ...); the
derivation is name-keyed, not path-keyed, so a schema that reuses a leaf
property name in two branches produces one `cv:hasInput` entry per
occurrence rather than a deduplicated one.

## Two options (B recommended as the starting point)

**Option A — accept generated JSON-LD, no schema change.** Ingestion keeps
accepting `metadata.jsonld` exactly as today; the only change is that a repo
may generate it with `manifest_to_jsonld` instead of writing it by hand. No
work needed on regles.data.gouv.fr's side beyond documenting this path.

**Option B — accept the unified manifest directly.** Ingestion accepts a
Datapi-shaped manifest (single-algorithm or `algorithms[]` package) and
derives `cv:hasInput`/`cpsv:produces` itself by flattening
`input_schema`/`output_schema` (same algorithm as `manifest_to_jsonld`) —
no separate output file to generate or keep in sync anywhere, for either
side.

Option B removes one moving part end-to-end, at the cost of
regles.data.gouv.fr taking on the JSON Schema → CPSV-AP derivation itself
(and its edge cases, like the name-collision caveat above). Option A is
zero-risk for regles.data.gouv.fr and available immediately since it only
changes how the existing input format gets produced.

Happy to share `catalog/jsonld_converter.py`'s conversion logic (~250
lines, no dependencies beyond the stdlib) if useful as a starting point for
either option.
