# Tunery

Tunery builds printable PDF setbooks from existing sheet-music PDFs. Charts can
come from directories of standalone PDFs or from JSON-indexed songbooks.

## Configure libraries

Add an ordered `tunery.yaml` file to the project:

```yaml
- library: indexes/real-book.json
  source: books/Real Book.pdf
  shift: 0
  match: fuzzy
- library: handouts
  match: exact
```

The `source` field is required for indexed PDF libraries, while `shift` is
optional and defaults to `0`. Paths are relative to `tunery.yaml`. Later
libraries have higher lookup priority. If no project configuration is found,
Tunery uses the starting directory as a directory library.

A `library` may also point to a YAML collection file holding multiple library
records, with paths resolved relative to that file:

```yaml
- library: /path/to/rb-index/tunery.yaml
```

A `match` set on such a reference is a default: inner records that set their
own `match` win.

An indexed PDF library names one source PDF and its chart ranges:

```json
[
  {"title": "Autumn Leaves", "page": 39},
  {"title": "Song B", "page": 20, "pages": 2}
]
```

## Render a setbook

Create a layout such as `favorites.yaml`:

```yaml
- config:
    - library: favorite-tunes
      match: exact
- section: Set 1
  body:
    - title: Giant Steps
    - file: Lennie's Pennies.pdf
      notes: Watch the ending
```

Layout libraries are resolved relative to the layout and take priority over
project libraries.

```console
tunery render favorites.yaml
tunery lookup "Giant Steps"
```

Run `tunery --help` for command options.

## Developing

Follow [the repository guidelines](docs/GUIDELINES.md).

### Set up

- Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Create a virtual environment with `uv venv`.
- Install dependencies with `uv sync`.
- Optionally activate the environment with `source .venv/bin/activate`.

## License

Licensed under the Apache License, Version 2.0.

Copyright (C) 2024-2025 Sasha Ovsankin
