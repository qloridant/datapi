# Catala example

A minimal [Catala](https://catala-lang.org/) algorithm ("quotient familial"),
registered and executed through Datapi via `adapters/catala_adapter.py`. It
computes the same thing as `examples/python`, so the two can be compared
side by side.

Pattern : sources are compiled ahead of time to Python
and the generated package is checked in / built as an artifact, not
compiled on the fly by the API.

## Layout

- `src/quotient_familial.catala_fr` — the Catala source (source of truth).
- `generated/` — the Python translation, produced by the Catala compiler
  and lightly post-processed (see below). This is what
  `examples/catala/manifest.json`'s `entrypoint.target` points at.
- `clerk.toml` — project file for the `clerk` build tool (needed to compile
  the standard library modules `_fr` code depends on).

## How `generated/` was produced

Requires the [Catala toolchain](https://book.catala-lang.org/en/1-0-getting_started.html)
(`opam install catala`).

`generated/` has no extra pip dependencies beyond the standard library.

## Try it

```sh
python3 -c "
from adapters.catala_adapter import CatalaAdapter
import json
manifest = json.load(open('examples/catala/manifest.json'))
print(CatalaAdapter().execute_sync(manifest, 'run1',
    {'agent_revenu': 32000, 'agent_enfants': 2, 'conjoint_revenu': 0},
    exec_opts={'timeout_seconds': 10}))
"
```
