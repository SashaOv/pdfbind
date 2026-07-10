"""PDF rendering logic for combining PDFs with table of contents."""

from dataclasses import dataclass
import re
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field, PositiveInt, RootModel, ValidationError
from rapidfuzz import fuzz, process

from tunery.composer import Composer
from tunery.index import ChartMatch, Index
from tunery.library import (
    LibraryCollection,
    LibraryRecord,
    load_project_libraries,
)


class FileEntry(BaseModel):
    """A file entry specifying a PDF source and optional page range/notes.

    Either 'file' or 'title' must be provided. If only 'title' is provided,
    the file will be looked up in the index.
    """

    file: str | None = None
    title: str | None = None
    page: PositiveInt | None = None
    length: PositiveInt | None = None
    notes: str | None = None

    def model_post_init(self, __context) -> None:
        if not self.file and not self.title:
            raise ValueError("Either 'file' or 'title' must be provided")


class SectionEntry(BaseModel):
    """A section containing nested file entries or subsections."""

    section: str
    body: List["FileEntry | SectionEntry"] = Field(default_factory=list)


class ConfigEntry(BaseModel):
    """Configuration entry adding libraries for subsequent lookup."""

    config: list[LibraryRecord]


class OverrideConfigEntry(BaseModel):
    """Legacy configuration entry specifying an override directory."""

    override: str


class Layout(
    RootModel[List[ConfigEntry | OverrideConfigEntry | SectionEntry | FileEntry]]
):
    """The complete layout schema - a list of config, sections, and/or file entries."""

    pass


def resolve_path(path_str: str, base_dir: Path) -> Path:
    """
    Resolve a file path relative to base_dir if it's relative, otherwise return as-is.
    """
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


@dataclass
class ProcessEntryResult:
    """Base class for processing results."""
    title: str

    def format(self) -> str:
        """Format the result as a human-readable string."""
        raise NotImplementedError


@dataclass
class NotFoundResult(ProcessEntryResult):
    """Title not found."""
    hint: str | None = None  # e.g., 'Is this "Similar Title" in "Book"?'

    def format(self) -> str:
        msg = f'not found "{self.title}"'
        if self.hint:
            msg += f'. {self.hint}'
        return msg


@dataclass
class SuccessResult(ProcessEntryResult):
    """Successfully found and processed a file entry."""
    page: int
    source_path: Path
    source: str  # display name of the source (book name or directory path)
    matched_title: str | None = None  # set if fuzzy matched
    score: float | None = None  # set if fuzzy matched

    def format(self) -> str:
        if self.matched_title is not None:
            return f'matched  "{self.title}" with "{self.matched_title}" from {self.source} ({self.score:.0f}%)'
        else:
            return f'found    "{self.title}" in {self.source}'


def process_file_entry(
    entry: FileEntry,
    default_dir: Path,
    composer: Composer,
    index: Index | None = None,
    override_dir: Path | None = None,
    layout_path: Path | None = None,
    libraries: LibraryCollection | None = None,
) -> ProcessEntryResult:
    """
    Add the requested pages for an entry to the combined PDF.

    Returns: SuccessResult on success, NotFoundResult if title not found
             (both subclasses of ProcessEntryResult).
    """
    # Determine the input PDF path and page/length
    input_pdf_path: Path | None = None
    source: str
    matched_title: str | None = None
    score: float | None = None
    if entry.file:
        library_match = libraries.lookup_file(entry.file) if libraries else None
        input_pdf_path = (
            library_match.source
            if library_match is not None
            else resolve_path(entry.file, default_dir)
        )
        title = entry.title if entry.title else input_pdf_path.stem
        page = entry.page
        length = entry.length
        source = str(input_pdf_path.parent)
    else:
        # Look up in the index by title
        if not entry.title:
            raise ValueError("Entry must have either 'file' or 'title'")
        
        title = entry.title

        library_match = libraries.lookup_title(title) if libraries else None
        if library_match is not None:
            input_pdf_path = library_match.source
            page = entry.page if entry.page is not None else library_match.page
            length = (
                entry.length if entry.length is not None else library_match.length
            )
            source = str(input_pdf_path.parent)
            if library_match.score is not None:
                matched_title = library_match.title
                score = library_match.score
        else:
            input_pdf_path = None
        
        # Check override directory first if specified
        override_fuzzy_match: tuple[str, float] | None = None  # (matched_filename, score)
        if input_pdf_path is not None:
            pass
        elif override_dir and override_dir.exists():
            # Try exact match first
            override_file = override_dir / f"{title}.pdf"
            if not override_file.exists():
                # Try case-insensitive match
                title_lower = title.lower()
                for pdf_file in override_dir.glob("*.pdf"):
                    if pdf_file.stem.lower() == title_lower:
                        override_file = pdf_file
                        break
                else:
                    # No exact or case-insensitive match found, try fuzzy matching
                    pdf_files = list(override_dir.glob("*.pdf"))
                    if pdf_files:
                        # Normalize title for fuzzy matching (same as index normalization)
                        normalized_search = title.lower()
                        normalized_search = re.sub(r'[^\w\s]', '', normalized_search)
                        normalized_search = ' '.join(normalized_search.split())
                        
                        # Create mapping of normalized filenames to actual paths
                        file_map = {}
                        for pdf_file in pdf_files:
                            normalized_name = pdf_file.stem.lower()
                            normalized_name = re.sub(r'[^\w\s]', '', normalized_name)
                            normalized_name = ' '.join(normalized_name.split())
                            file_map[normalized_name] = pdf_file
                        
                        # Find best match
                        matches = process.extract(
                            normalized_search,
                            file_map.keys(),
                            scorer=fuzz.token_set_ratio,
                            score_cutoff=90,
                            limit=1,
                        )
                        if matches:
                            matched_name, score, _ = matches[0]
                            override_file = file_map[matched_name]
                            # Store matched filename and score for status message
                            override_fuzzy_match = (override_file.stem, score)
                        else:
                            override_file = None
                    else:
                        override_file = None
            
            if override_file and override_file.exists():
                # Use override file, skip index lookup
                input_pdf_path = override_file
                # If the layout entry doesn't specify a range, include the whole
                # override PDF by default. This is important for handouts where
                # the local PDF is the authoritative source and may be multi-page.
                page = entry.page
                length = entry.length
                # Get relative path for display
                try:
                    if layout_path:
                        override_rel = override_file.relative_to(layout_path.parent)
                        override_path = override_rel.parent
                    else:
                        override_path = override_file.parent
                except ValueError:
                    override_path = override_file.parent
                
                # Check if this was a fuzzy match
                source = str(override_path)
                if override_fuzzy_match is not None:
                    matched_title, score = override_fuzzy_match
            else:
                # No override file found, fall back to index lookup
                if index is None:
                    # Check for fuzzy matches in override directory as hints
                    fuzzy_hints = []
                    if override_dir and override_dir.exists():
                        pdf_files = list(override_dir.glob("*.pdf"))
                        if pdf_files:
                            normalized_search = title.lower()
                            normalized_search = re.sub(r'[^\w\s]', '', normalized_search)
                            normalized_search = ' '.join(normalized_search.split())
                            file_map = {}
                            for pdf_file in pdf_files:
                                normalized_name = pdf_file.stem.lower()
                                normalized_name = re.sub(r'[^\w\s]', '', normalized_name)
                                normalized_name = ' '.join(normalized_name.split())
                                file_map[normalized_name] = pdf_file
                            matches = process.extract(
                                normalized_search,
                                file_map.keys(),
                                scorer=fuzz.token_set_ratio,
                                score_cutoff=70,  # Lower threshold for hints
                                limit=1,
                            )
                            if matches:
                                matched_name, score, _ = matches[0]
                                fuzzy_hints.append(f'"{file_map[matched_name].stem}"')
                    hint = f'Is this {fuzzy_hints[0]}?' if fuzzy_hints else None
                    return NotFoundResult(title=title, hint=hint)

                # Exact match (case-insensitive, highest priority wins)
                location = index.lookup(title)
                exact_match = location is not None
                
                # If exact match failed, try fuzzy matching
                index_fuzzy_match_used: ChartMatch | None = None
                if not location:
                    fuzzy_matches = index.lookup_fuzzy_edit_distance(title, score_cutoff=90, limit=1)
                    if fuzzy_matches:
                        index_fuzzy_match_used = fuzzy_matches[0]
                        location = index_fuzzy_match_used.location
                
                if not location:
                    # Not found - get hints from fuzzy matches (even below threshold)
                    fuzzy_matches = index.lookup_fuzzy_edit_distance(title, score_cutoff=70, limit=1)
                    if fuzzy_matches:
                        hint_match = fuzzy_matches[0]
                        hint_title = hint_match.matched_title
                        hint_source = Path(hint_match.location.source_path).stem
                        hint = f'Is this "{hint_title}" in "{hint_source}"?'
                    else:
                        hint = None
                    return NotFoundResult(title=title, hint=hint)

                input_pdf_path = Path(location.source_path)
                source = input_pdf_path.stem
                if not exact_match:
                    # index_fuzzy_match_used was set earlier and is not None
                    assert index_fuzzy_match_used is not None
                    matched_title = index_fuzzy_match_used.matched_title
                    score = index_fuzzy_match_used.score
                # Use entry's page/length if specified, otherwise use from index
                page = entry.page if entry.page else location.page
                length = entry.length if entry.length else location.length
        else:
            # No override directory, proceed with index lookup
            if index is None:
                raise ValueError(
                    f"Cannot look up '{title}': no index available. "
                    "Run 'tunery index <dir>' first."
                )

            # Exact match (case-insensitive, highest priority wins)
            location = index.lookup(title)
            exact_match = location is not None
            
            # If exact match failed, try fuzzy matching
            index_fuzzy_match: ChartMatch | None = None
            if not location:
                fuzzy_matches = index.lookup_fuzzy_edit_distance(title, score_cutoff=90, limit=1)
                if fuzzy_matches:
                    index_fuzzy_match = fuzzy_matches[0]
                    location = index_fuzzy_match.location
            
            if not location:
                # Not found - get hints from fuzzy matches (even below threshold)
                fuzzy_matches = index.lookup_fuzzy_edit_distance(title, score_cutoff=70, limit=1)
                if fuzzy_matches:
                    hint_match = fuzzy_matches[0]
                    hint_title = hint_match.matched_title
                    hint_source = Path(hint_match.location.source_path).stem
                    hint = f'Is this "{hint_title}" in "{hint_source}"?'
                else:
                    hint = None
                return NotFoundResult(title=title, hint=hint)

            input_pdf_path = Path(location.source_path)
            source = input_pdf_path.stem
            if not exact_match:
                # index_fuzzy_match was set earlier and is not None
                assert index_fuzzy_match is not None
                matched_title = index_fuzzy_match.matched_title
                score = index_fuzzy_match.score
            # Use entry's page/length if specified, otherwise use from index
            page = entry.page if entry.page else location.page
            length = entry.length if entry.length else location.length

    assert input_pdf_path is not None
    entry_page = composer.add(
        title=title,
        source=input_pdf_path,
        start=page,
        pages=length,
        notes=entry.notes,
    )

    return SuccessResult(
        title=title,
        page=entry_page,
        source_path=input_pdf_path,
        source=source,
        matched_title=matched_title,
        score=score,
    )


def render(
    layout_path: Path,
    output: Path,
    index_path: Path | None = None,
    override_dir: Path | None = None,
) -> None:
    """Combine PDFs according to the YAML layout file."""
    try:
        with open(str(layout_path), "r") as file:
            file_content = file.read()
            raw_data = yaml.safe_load(file_content)
    except yaml.YAMLError as e:
        # Add file path and line information to YAML parsing errors
        error_msg = f"YAML parsing error in {layout_path}"
        # Some YAML errors have problem_mark with line/column info
        problem_mark = getattr(e, "problem_mark", None)
        if problem_mark is not None:
            error_msg += f" at line {problem_mark.line + 1}, column {problem_mark.column + 1}"
        error_msg += f": {e}"
        raise ValueError(error_msg) from e

    # Parse and validate the YAML records using Pydantic
    try:
        layout = Layout.model_validate(raw_data)
    except ValidationError as e:
        # Use Pydantic's built-in error formatting
        error_msg = f"Validation error in {layout_path}:\n{e}"
        raise ValueError(error_msg) from e

    libraries = load_project_libraries(layout_path.parent)

    # Extract config entries and legacy override directory
    layout_entries: list[SectionEntry | FileEntry] = []
    for record in layout.root:
        if isinstance(record, ConfigEntry):
            for library_record in record.config:
                libraries.add(library_record.load(layout_path.parent))
        elif isinstance(record, OverrideConfigEntry):
            override_dir = resolve_path(record.override, layout_path.parent)
        else:
            # Keep non-config entries for processing
            layout_entries.append(record)

    # Get the directory of the YAML file for resolving relative paths
    default_dir = layout_path.parent.resolve()
    # By default, treat the layout file directory as the override directory.
    # This means PDFs next to the YAML (e.g., handouts) take precedence over
    # indexed songbooks when a `title:` is provided without an explicit `file:`.
    if override_dir is None:
        override_dir = default_dir

    # Open index if it exists (for title lookups)
    index: Index | None = None
    if index_path and index_path.exists():
        index = Index(index_path)

    def process_items(items: list[SectionEntry | FileEntry]) -> None:
        """Process layout items recursively."""
        for item in items:
            if isinstance(item, SectionEntry):
                composer.start_section(item.section)
                process_items(item.body)
                composer.end_section()
            else:
                result = process_file_entry(
                    item,
                    default_dir,
                    composer,
                    index,
                    override_dir,
                    layout_path,
                    libraries,
                )
                print(result.format())

    try:
        with Composer(output, autosave=False) as composer:
            process_items(layout_entries)
            composer.save()
    finally:
        if index:
            index.close()


def lookup_and_extract(
    title: str,
    output: Path | None,
    index_path: Path,
) -> None:
    """
    Look up a title in the index and extract to PDF.

    If multiple matches are found, lists them and exits without extraction.
    If a single match is found, extracts the pages to the output PDF.

    Args:
        title: The title (or part of title) to search for.
        output: Output path - if file, use as-is; if directory, save <title>.pdf there;
                if None, save <title>.pdf in current directory.
        index_path: Path to the SQLite index file.
    """
    libraries = load_project_libraries()
    library_match = libraries.lookup_title(title)
    if library_match is not None:
        matched_title = library_match.title
        output_path = (
            Path(f"{matched_title}.pdf")
            if output is None
            else output / f"{matched_title}.pdf"
            if output.is_dir()
            else output
        )
        print(f'Found "{matched_title}" in "{library_match.source.parent}"')
        with Composer(output_path, autosave=False) as composer:
            composer.add(
                matched_title,
                library_match.source,
                start=library_match.page,
                pages=library_match.length,
            )
            composer.save()
        print(f"Extracted to: {output_path}")
        return

    if not index_path.exists():
        print(f"Index not found: {index_path}")
        print("Run 'tunery index <index.json>' first to build the index.")
        return

    with Index(index_path) as index:
        # First try exact match
        exact_location = index.lookup(title)
        if exact_location:
            # Single exact match - extract it
            matched_title = title
            location = exact_location
        else:
            # Try fuzzy matching
            matches = index.lookup_fuzzy_edit_distance(title, score_cutoff=70, limit=10)

            if not matches:
                print(f'No matches found for "{title}"')
                return

            if len(matches) > 1:
                # Multiple matches - list them and exit
                print(f'Found {len(matches)} matches for "{title}":')
                for i, match in enumerate(matches, 1):
                    source_name = Path(match.location.source_path).stem
                    pages_str = f"{match.location.length} page" if match.location.length == 1 else f"{match.location.length} pages"
                    print(f'  {i}. "{match.matched_title}" in "{source_name}" (page {match.location.page}, {pages_str}) - {match.score:.0f}%')
                print("Run again with exact title to extract.")
                return

            # Single fuzzy match
            matched_title = matches[0].matched_title
            location = matches[0].location

        # Determine output path
        if output is None:
            output_path = Path(f"{matched_title}.pdf")
        elif output.is_dir():
            output_path = output / f"{matched_title}.pdf"
        else:
            output_path = output

        # Extract pages
        source_name = Path(location.source_path).stem
        pages_str = f"{location.length} page" if location.length == 1 else f"{location.length} pages"
        print(f'Found "{matched_title}" in "{source_name}" (page {location.page}, {pages_str})')

        with Composer(output_path, autosave=False) as composer:
            composer.add(
                matched_title,
                Path(location.source_path),
                start=location.page,
                pages=location.length,
            )
            composer.save()

        print(f"Extracted to: {output_path}")
