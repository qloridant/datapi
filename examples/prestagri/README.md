# Prest'Agri example

A real-world [Catala](https://catala-lang.org/) algorithm vendored from
[Prest'Agri](https://github.com/betagouv/prestagri) (Apache-2.0), registered
and executed through Datapi via `adapters/catala_adapter.py`. Where
`examples/catala` is a toy scope with only flat scalar fields, this one
("aide à la scolarité") exercises the parts of `CatalaAdapter`'s marshalling
that scope doesn't: a nested `CatalaStruct` field (`Menage` containing a
`List[FoyerFiscal]`), an `Option[Trajet]` field, and `List[CatalaEnum]`
outputs (`criteres_applicables`).

Pattern: same as `examples/catala` — sources are compiled ahead of time to
Python and the generated package is checked in / built as an artifact, not
compiled on the fly by the API.

## Layout

- `src/` — the Catala sources this scope depends on (source of truth),
  copied from `external_repositories/prestagri/catala/src`: the
  `aide_scolarite` module and the `commun` structures/quotient familial
  modules it imports.
- `generated/` — the Python translation, copied as-is from
  `external_repositories/prestagri/backend/app/catala/generated` (produced
  there by the Catala compiler). This is what
  `examples/prestagri/manifest.json`'s `aide_scolarite` algorithm entry's
  `entrypoint.target` points at.
- `clerk.toml` — project file for the `clerk` build tool, copied from the
  upstream `catala/` project, kept for reference on how `generated/` was
  produced upstream.

## Try it

`examples/prestagri/manifest.json` is a **package** manifest (see
`catalog/manifest.schema.json` and `docs/INTEGRATION.md`, section "Un dépôt
qui expose plusieurs algorithmes") — Prest'Agri's real
[`metadata.jsonld`](https://github.com/betagouv/prestagri) registered on
[regles.data.gouv.fr](https://github.com/datagouv/regles.data.gouv.fr)
describes both a quotient-familial and an aide-scolarite service under one
aggregator, and only the latter is vendored/registered here so far. Use
`catalog.manifest_loader.load_manifests(...)` to get the flattened algorithm
entry rather than reading the file as a single-algorithm manifest:

```sh
python3 -c "
from adapters.catala_adapter import CatalaAdapter
from catalog.manifest_loader import load_manifests
manifest = load_manifests('examples/prestagri/manifest.json')[0]
print(CatalaAdapter().execute_sync(manifest, 'run1', manifest['sample_inputs'],
    exec_opts={'timeout_seconds': 10}))
"
```

`input_schema`/`output_schema` in the manifest were generated with
`CatalaAdapter().infer_manifest_schemas(...)` (see
`docs/INTEGRATION.md`, section "Générer input_schema/output_schema
automatiquement") rather than hand-written, since this scope's nested types
make hand-transcription error-prone.
