---
refines: docs/SPEC.md
---

# Library-based chart lookup

## Motivation

Represent all searchable chart collections through a common Library
abstraction. Load indexes directly into memory instead of requiring users to
build and maintain a separate SQLite database.

## Concepts

### Library

A Library is a searchable collection of tunes. A lookup returns the source PDF,
starting page, page count, and canonical title needed to add the tune to an
output document.

Libraries support **exact** and **fuzzy** title lookup.


### Directory library

Treat a directory as a collection of standalone PDF files. Derive tune titles
from PDF filenames.

### Indexed PDF library

Use a JSON file that names one source PDF and maps tune titles to page ranges.
Resolve the source PDF path relative to the JSON file.

### Searching multiple libraries

When multiple libraries are specified, the later library has higher search priority.

## Configuration

### Project configuration

The project configuration file is named `tunery.yaml`. Tunery searches for it
starting in the directory of the layout file and then in each parent directory,
up to 8 parent levels. Commands without a layout file start from the current
working directory. The first file found is the project configuration; Tunery
does not merge multiple project configuration files.

If no project configuration is found, print the informational message
`Project configuration was not found, using defaults` and use the current
starting directory as a directory Library.

The project configuration is an ordered list of Library records. Each record
contains a Library path and its matching mode:

```yaml
- library: Indexes/realbook.json
  match: fuzzy
- library: ../Handouts
  match: exact
```

`match` is optional and defaults to `exact`. An `exact` Library only returns
normalized exact matches. A `fuzzy` Library tries an exact match first and then
fuzzy matching. Match mode belongs to the Library record, not to individual
layout entries.

Resolve paths in `tunery.yaml` relative to the directory containing that file.
If a library path is a directory, treat it as a directory Library. If it is a
JSON file, treat it as an indexed PDF Library. Reject paths of any other type
with a visible error.

An indexed PDF Library JSON file is self-contained:

```json
{
  "source": "../Books/RealBook.pdf",
  "shift": 0,
  "tunes": [
    {"title": "Autumn Leaves", "page": 39},
    {"title": "Song B", "page": 20, "pages": 2}
  ]
}
```

`source` is required and resolves relative to the index JSON file. `shift` is
optional and defaults to `0`. `tunes` contains the indexed tune entries.

### Layout library records

A layout Config record can add a Library to the libraries loaded from project
configuration. It uses the same Library record format as project configuration.
Replace the existing `override` Config record with `library` records:

```yaml
- config:
    - library: ../../Handouts
      match: exact
    - library: ../../Indexes/realbook.json
      match: fuzzy
```

Resolve paths in a layout `library` record relative to the layout file. Add
layout libraries in record order after project libraries, so they have higher
search priority. A layout can contain multiple `library` records.

## Build 1 — Search directory libraries from the application

- Discover `tunery.yaml` from the layout directory through at most 8 parent
  directories. Commands without a layout start from the current working
  directory.
- When no project configuration exists, inform the user and use the current
  starting directory as the default directory Library.
- Let users configure a directory path as a Library and search its standalone PDFs
  by exact or fuzzy tune title.
- Let each Library record select `exact` or `fuzzy` matching, defaulting to
  `exact`.
- Let layout `library` records add directory libraries after project libraries,
  replacing the existing `override` Config record.
- Resolve layout `title:` entries and `lookup` command titles through configured
  directory libraries.
- Resolve layout `file:` entries through directory libraries as well. Only
  directory libraries participate in `file:` resolution; indexed PDF libraries
  do not.
- Preserve title normalization and fuzzy matching behavior.
- Report missing directories and unresolved entries as visible errors.
- Introduce the Library interface and lookup result contract as part of this
  user-visible directory search capability.

## Build 2 — Search indexed PDFs without building a database

- Let users configure an indexed PDF Library with a JSON path that identifies
  its source PDF and tune entries.
- Let project configuration and layout `library` records contain indexed PDF
  libraries.
- Load JSON indexes directly into memory when rendering or looking up tunes;
  do not require a separate database-building step.
- Let users search an ordered collection of directory and indexed PDF
  libraries, with later libraries taking priority.
- Express override behavior through library ordering instead of a separate
  lookup mechanism.
- Report malformed indexes and missing source PDFs as visible errors.
- Preserve page ranges, title normalization, fuzzy matching, and duplicate-title
  priority behavior.

--- Implemented / Next ---

## Build LIB3 — Simplify the library workflow

**Material improvement:** Tunery renders and looks up charts exclusively through
automatically discovered project and layout libraries. The SQLite index and
override workflows disappear from the CLI, runtime, and documentation.

**Acceptance check:**

- CLI help exposes `render` and `lookup`, but no `index` command, `--index`, or
  `--override`.
- Integration tests render and extract from discovered directory and indexed
  PDF libraries without creating or opening SQLite.
- Runtime code and user documentation contain no SQLite index workflow.
- The full test suite passes.

### Patches

- [x] **P1 — Replace override inputs with library ordering.** Remove the layout
  `override` record, `--override`, and override-specific rendering paths.
  Preserve local-handout priority through ordered directory-library records.
  Verify render and CLI tests.
- [x] **P2 — Retire the SQLite index pipeline.** Remove the `index` command,
  `--index`, SQLite fallback paths, `tunery/index.py`, and obsolete index tests.
  Make `lookup` use discovered libraries exclusively while preserving
  output-path and multiple-title behavior. Verify CLI, library, and render tests
  plus a repository scan for runtime SQLite references. Keep at least one lookup
  title required instead of exposing the CLI framework's empty-list option.
- [ ] **P3 — Document the library-only workflow.** Update the README and root
  spec with `tunery.yaml`, layout library records, lookup precedence, and direct
  JSON-index loading; remove database-building instructions. Run the full
  acceptance check.

## Completion

- Consolidate concepts under a single Concepts section.
- Describe each input format only under Configuration / Inputs.
- Describe lookup precedence only under Behavior.
- Reference the Library definition instead of redefining indexes in multiple
  sections.
- Fold stable behavior into the root spec and retire this change spec after all
  Builds are implemented.
