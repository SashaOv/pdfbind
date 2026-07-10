# Tunery
**Goal**: build a single printable PDF “setbook” (setlist booklet) by stitching together pages from a collection of existing sheet-music PDFs.

## Concepts

### Layout
References charts either by explicit file path or by title, resolved via file lookup and/or index.

### Index
Is a local SQLite index of chart titles → (PDF file, page, page-count), built from a set of existing files (books).

### Library
A set of tunes. Types of libraries:

- Directory. A tune is searched by file name $tune_name.pdf
- Indexed PDF: a PDF file + JSON index which maps tunes to pages in file.
- Collection of indexed PDFs

Search in library could be **exact**, by exact name, or **fuzzy**, using fuzzy search algorithms.


## Deployable
`tunery` — CLI

`tunery` — Python package API

Usage: `tunery COMMAND ...`

Commands:
- **index** `INDEX_JSON` — build the SQLite index at `~/.cache/tunery/index.sqlite`
  - `INDEX_JSON` is the path to the main `index.json` file (format below).
- **render** `LAYOUT_YAML` `[-o OUTPUT_PDF] [--index INDEX_SQLITE] [--override DIR]` — build a combined PDF from a layout file.
  - `-o/--output`: default is `<layout_basename>.pdf` next to the YAML.
  - `--index`: path to SQLite index (default `~/.cache/tunery/index.sqlite`). If missing/unavailable, title-based lookups can still succeed via overrides.
  - `--override`: directory with PDFs that should take precedence for `title:` lookups.
- **lookup** `TITLE_PART` - lookup a title in the index and if found, 
  generate a single PDF with the title (as found in the source).
  - `-o/--output`: if file, use this file path, if directory, put `<found_title>.pdf` in that directory, default is `<layout_basename>.pdf` in current directory.

Python API:
- Import `Composer` from the package root: `from tunery import Composer`.
- Construct `Composer(output_path)` to create a programmatic setbook builder.
- Call `add(title, source, start=None, pages=None)` to append pages from an explicit PDF source. `start` uses the same page-numbering behavior as layout `page`; `pages` uses the same behavior as layout `length`. If both are omitted, include the whole PDF.
- Call `start_section(title)` and `end_section()` to group subsequent additions under nested outline bookmarks.
- Save the output PDF after additions and section changes. Use `close()` or a context manager to release the underlying PDF object.

## Configuration / Inputs

### Main index (`index.json`)
JSON file containing an array of **book entries**:

```json
[
  {
    "source": "Books/RealBook.pdf",
    "index": "Indexes/realbook.json",
    "shift": 0
  }
]
```

Fields:
- **source** (required): path to the source PDF, relative to `index.json`.
- **index** (required): path to the per-book index JSON file, relative to `index.json`.
- **shift** (optional): integer page offset added to every entry’s `page` from the per-book index.
- **title / edition / volume** (optional): accepted but currently not used by the implementation.

### Per-book index JSON
Each referenced `index` file is a JSON array of entries:

```json
[
  {"title": "Autumn Leaves", "page": 39},
  {"title": "Song B", "page": 20, "pages": 2}
]
```

Fields:
- **title** (required): chart title.
- **page** (required, 1-based): page label/number where the chart starts.
- **pages** (optional, default 1): number of pages to include for the chart.

### Layout YAML (render input)
YAML file containing a list of records. Records can be:

- **Config record** (sets override directory; takes precedence over `--override`):

```yaml
- override: ../../Handouts
```

- **Flat file record** (one item in the PDF outline):

```yaml
- file: Songbook.pdf
  page: 12
  length: 2
  title: Latin Medley
  notes: "Watch ending — fermata on bar 32"
```

- **Section record** (creates a section bookmark with nested child bookmarks):

```yaml
- section: Set 1
  body:
    - title: Country           # resolved via overrides/index
    - file: Groove.pdf         # explicit file
      title: Groove Standard
    - section: Medley          # nested subsection
      body:
        - title: Song A
        - title: Song B
```

Sections can be nested arbitrarily deep. Each section creates an outline (bookmark) node with its body items as children.

Fields for a file record:
- **file** (optional): PDF path (absolute, or relative to the YAML file directory).
- **title** (optional): display title and/or lookup key. Either `file` or `title` must be present.
- **page** (optional): start page (see “Page numbering” below).
- **length** (optional): number of pages to include. If omitted and `page` is set, defaults to 1. If both `page` and `length` are omitted, the whole PDF is included.
- **notes** (optional): if present, notes are drawn at the bottom of every included page.

## Behavior

### Index building
- Builds `~/.cache/tunery/index.sqlite` (overwriting any existing DB).
- Resolves each book `source` to an absolute path and stores it in the DB.
- Titles are stored normalized to **lowercase** for case-insensitive matching.
- **Priority**: later book entries in `index.json` have higher priority; exact lookups return the highest-priority match.
- Prints a short summary (`Indexed <n> charts...`) and lists duplicate titles (case-insensitive).
- Missing/malformed per-book index files or missing source PDFs are skipped with a printed warning.

### Rendering / lookup rules
For each layout entry:
- If **`file:` is present**, it is used directly (no index lookup).
- If **only `title:` is present**, resolution is:
  - **Override directory first**:
    - Default override dir is the layout YAML directory (so “handout PDFs next to the YAML” win by default).
    - If `override:` config record exists or `--override` is passed, that directory is used instead.
    - Matching order: exact `<title>.pdf`, then case-insensitive filename match, then fuzzy filename match.
  - **Index lookup second** (only if an index file exists at `--index`):
    - Exact match is case-insensitive.
    - If exact fails, fuzzy match is attempted (weighted ratio combining multiple strategies; normalization: lowercase, punctuation removed, whitespace normalized).
    - If a title exists in multiple PDFs, Tunery uses the source PDF that comes later in `index.json` (higher priority).
- If no match is found, Tunery prints a “not found … is this …?” hint (based on fuzzy matching) and skips the entry (render continues).

### Page numbering
When `page` is specified for extraction, Tunery first tries to interpret it as a **PDF page label** (for decimal page-label ranges), and maps it to a physical 0-based page index. If no label mapping exists (or the label isn’t found), it falls back to treating `page` as a 1-based physical page index. (Any per-book `shift` is applied when building the SQLite index.)

### Output
- Produces a single PDF at `OUTPUT_PDF`.
- Adds a PDF outline (bookmarks):
  - flat entries become top-level outline items.
  - sections become top-level outline items with children pointing to the first included page of each body entry.
  - empty sections are allowed (their destination defaults to page 0).

### Errors
- YAML parsing errors are raised as `ValueError` including file path and (when available) line/column.
- Schema validation errors (wrong record shapes/fields) are raised as `ValueError` with formatted validation details.
