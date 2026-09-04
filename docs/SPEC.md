# Tunery

**Goal:** Build a printable PDF setbook by stitching together pages from
existing sheet-music PDFs.

## Concepts

### Layout

A layout is an ordered YAML description of charts and nested sections in an
output setbook. A chart can name a PDF file or a tune title.

### Library

A Library is a searchable collection of tunes. A successful lookup returns the
source PDF, canonical title, starting page, and page count.

Tunery supports:

- **Directory libraries:** standalone PDFs whose filenames provide tune titles.
- **Indexed PDF libraries:** a source PDF paired by its library record with a
  JSON mapping from tune titles to page ranges.
- **Library collections:** ordered directory and indexed PDF libraries searched
  as one collection, optionally loaded from a YAML collection file.

Each library uses either normalized exact matching or exact-then-fuzzy
matching.

## Deployable

`tunery` is both a CLI and a Python package.

### CLI

- **render** `LAYOUT_YAML [-o OUTPUT_PDF]` builds a setbook. The default output
  is `<layout_basename>.pdf` next to the layout.
- **lookup** `TITLE... [-o OUTPUT]` extracts requested titles. If `OUTPUT` is a
  directory, Tunery writes `<canonical_title>.pdf` inside it. If it is a file,
  Tunery uses it as-is. The default is
  `<canonical_title>.pdf` in the current directory.

### Python API

- Import `Composer`, `DirectoryLibrary`, `IndexedPdfLibrary`, `Library`,
  and `LibraryCollection` from the package root.
- Construct `Composer(output_path)` to build a setbook programmatically.
- Call `add(title, source, start=None, pages=None)` to append pages from a PDF.
- Call `start_section(title)` and `end_section()` to create nested outline
  sections.
- Save the output after additions. Use `close()` or a context manager to
  release the PDF.

## Configuration / Inputs

### Project configuration

The project configuration file is named `tunery.yaml`. It contains an ordered
list of library records:

```yaml
- library: indexes/real-book.json
  source: books/Real Book.pdf
  shift: 0
  match: fuzzy
- library: handouts
  match: exact
```

Fields:

- **library** (required): a directory, tune-index JSON file, or YAML library
  collection file.
- **source** (required for indexed PDF libraries): source PDF path. Directory
  libraries and YAML collections must not specify `source`.
- **shift** (optional): integer added to every indexed tune page; defaults to
  `0`. Directory libraries and YAML collections must not specify `shift`.
- **match** (optional): `exact` or `fuzzy`; defaults to `exact`.

Resolve both `library` and `source` paths relative to the file containing the
library record: `tunery.yaml` for project libraries or the layout file for
layout libraries.

A YAML library collection file contains an ordered list of library records
using the same schema, for example `/path/to/rb-index/tunery.yaml`. Referencing
it includes all of its libraries in order at that position:

```yaml
- library: /path/to/rb-index/tunery.yaml
```

Resolve paths inside the collection relative to the collection file's real
location (after dereferencing symlinks). Collections may nest; circular includes
are an error. A `match` set on the collection reference applies only to inner
records that do not set `match` explicitly; an inner `match` always wins.

### Indexed PDF library

An indexed PDF library JSON file is an array of tune records:

```json
[
  {"title": "Autumn Leaves", "page": 39},
  {"title": "Song B", "page": 20, "pages": 2}
]
```

Fields:

- **title** (required): canonical tune title.
- **page** (required): positive starting page before applying the library
  record's `shift`.
- **pages** (optional): positive page count; defaults to `1`.

Tunery reads this array directly and pairs it with the `source` and optional
`shift` from the library record.

### Layout YAML

A layout is a list containing config, chart, and section records.

A config record adds libraries after the project libraries:

```yaml
- config:
    - library: ../../handouts
      match: exact
    - library: ../../indexes/real-book.json
      source: ../../books/Real Book.pdf
      match: fuzzy
```

Resolve layout `library` and `source` paths relative to the layout file.

A chart record names a file, a title, or both:

```yaml
- file: Songbook.pdf
  page: 12
  length: 2
  title: Latin Medley
  notes: "Watch ending — fermata on bar 32"
```

Chart fields:

- **file** (optional): PDF path or filename. Either `file` or `title` is
  required.
- **title** (optional): display title and title lookup key.
- **page** (optional): positive starting page.
- **length** (optional): positive page count.
- **notes** (optional): text drawn at the bottom of every included page.

A section creates a nested PDF outline:

```yaml
- section: Set 1
  body:
    - title: Country
    - file: Groove.pdf
      title: Groove Standard
    - section: Medley
      body:
        - title: Song A
        - title: Song B
```

Sections can nest to any depth and may be empty.

## Behavior

### Configuration discovery

For `render`, search for `tunery.yaml` starting in the layout directory and
then through at most eight parent directories. For commands without a layout,
start from the current working directory. Use the first configuration found;
do not merge project configurations.

If the found `tunery.yaml` is a symbolic link, dereference it and resolve
relative `library` and `source` paths against the real file's directory.

If no project configuration exists, print
`Project configuration was not found, using defaults` and use the starting
directory as a directory library.

### Lookup precedence and matching

Load project libraries first, followed by layout libraries in record order.
Search from last to first, so later libraries have higher priority.

For `title:` entries and the `lookup` command:

1. Try each library in priority order.
2. Normalize exact matches by lowercasing, removing punctuation, and collapsing
   whitespace.
3. If a library uses `fuzzy` matching and exact matching fails, try fuzzy
   title matching.
4. Return the first matching library result.

For `file:` entries, search directory libraries in the same priority order.
Indexed PDF libraries do not participate in file lookup. If no directory
library resolves the file, resolve it relative to the layout.

Directory title lookup considers PDFs directly inside the library directory.
Indexed PDF lookup preserves the indexed page range and adds the library
record's `shift` to the starting page. The resulting page must be positive.

### Rendering and lookup

Rendering processes layout records in order, adds bookmarks for charts and
sections, and prints a visible result for each chart. An unresolved title prints
`not found "<title>"`, skips that chart, and continues rendering.

`lookup` prints the discovered source and extracts the matched page range. An
unresolved title prints `No matches found for "<title>"` and creates no file.

### Page numbering

When `page` is set, first interpret it as a decimal PDF page label. If the
label is unavailable, treat it as a 1-based physical page number. If `length`
is omitted while `page` is set, include one page. If both are omitted, include
the whole PDF.

### Output

- Produce one combined PDF for `render`.
- Add top-level bookmarks for flat chart entries.
- Add nested bookmarks for sections and their bodies.
- Point an empty section at page 0.

### Errors

- Raise visible errors for missing library paths, malformed configuration,
  malformed indexed PDF JSON, malformed YAML collections, circular collection
  includes, missing source PDFs, invalid page ranges, and library records that
  omit required indexed-PDF fields or attach indexed-only fields to a directory
  library or YAML collection.
- Include the layout path and available line/column information in YAML parsing
  errors.
- Include the layout path in schema validation errors.
