# Draft issue for datagouv/regles.data.gouv.fr

**Not opened yet** — for review before posting. Title suggestion below.

---

**Title:** Adopt Datapi's manifest (single or multi-algorithm) as the one file format for registering services — no metadata.jsonld, no converter

## Context

[Datapi](https://github.com/datagouv/datapi) registers algorithms via a
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
(`catalog/manifest.schema.json`) and, wherever a term already exists in
CPSV-AP/DCAT, to name the field with that term directly —
`dct:identifier`, `cv:hasChannel`, `dct:source` — instead of inventing a
Datapi-only synonym that something would later have to translate. Fields
stay Datapi-specific only where no core vocabulary covers them: `runtime`,
`entrypoint`, `resources` describe *how to execute* the algorithm, which is
outside CPSV-AP's scope.

This issue proposes regles.data.gouv.fr read that manifest directly as its
ingestion input, so there is exactly **one file, in one format**, understood
natively by both sides — not two files kept in sync by a converter. We
deliberately don't want a `metadata.jsonld`-shaped adapter/export step
sitting between the two systems: every predicate the manifest can express in
CPSV-AP terms, it expresses that way already, so there's nothing left for a
conversion layer to do except the one mapping that's unavoidable because no
vocabulary substitutes for it — turning JSON Schema (`input_schema`/
`output_schema`) into `cv:hasInput`/`cpsv:produces`. That mapping belongs in
regles.data.gouv.fr's ingestion code as a direct read of the manifest, not as
a separate file-to-file conversion step.

## Worked example: examples/prestagri/

[`examples/prestagri/manifest.json`](../examples/prestagri/manifest.json) is
Prest'Agri's real `metadata.jsonld`, one-time-migrated into a Datapi package
manifest (shared `org`/`dct:source` at the top, one entry per algorithm
under `algorithms`) that carries the same CPSV-AP predicates directly —
after this migration, `metadata.jsonld` is retired, not kept in sync:

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
      "dct:title": "Aide à la scolarité (Prest'Agri)",
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

Reading that manifest, regles.data.gouv.fr's ingestion already has
`dct:identifier`, `dct:title`, `cv:hasChannel`, and `dct:source` as plain
fields — no JSON-LD node lookup, no `@context` resolution, nothing to parse
beyond the manifest itself. (`id` stays Datapi-only and distinct from
`dct:identifier` — it's the technical handle used for routing and execution,
e.g. `/execute/{id}`, not a public-service identifier.) The one thing it
still has to compute
is `cv:hasInput`/`cpsv:produces`, by flattening `input_schema`/
`output_schema` (plain JSON Schema, which has no CPSV-AP equivalent to read
off directly):

```json
"cv:hasInput": [ "...derived from input_schema..." ],
"cpsv:produces": [ "...derived from output_schema..." ]
```

That derivation doesn't match the original hand-written `metadata.jsonld`
parameter list 1:1 in this case — Prest'Agri's public HTTP API takes
higher-level inputs (`agent_revenu`, `adresse_agent`, ...) than the raw
Catala scope vendored into Datapi (`foyer_fiscal_agent`,
`trajet_depuis_domicile_agent`, ...); it's name-keyed, not path-keyed, so a
schema that reuses a leaf property name in two branches produces one
`cv:hasInput` entry per occurrence rather than a deduplicated one.

## Proposal

Ingestion accepts a Datapi-shaped manifest (single-algorithm or
`algorithms[]` package) as the *only* registration input. No
`metadata.jsonld`, hand-written or generated, and no converter/adapter
translating one file into the other — every CPSV-AP-expressible field is
already named with its CPSV-AP predicate in the manifest, so ingestion reads
it as-is; only the JSON Schema → `cv:hasInput`/`cpsv:produces` flattening
above is genuinely new logic, because no vocabulary already covers "the
shape of these input/output parameters."

This does mean regles.data.gouv.fr takes on that one flattening step (and
its edge cases, like the name-collision caveat above) instead of it living
in Datapi. In exchange there is exactly one file format end-to-end, and nothing
downstream of it to keep in sync.

Happy to share the ~40 lines this flattening takes in
`catalog/jsonld_converter.py` (`_flatten_to_field_nodes` /
`_algorithm_to_service_node`) as a reference if useful — not as a dependency
to adopt, just worked logic to start from.
