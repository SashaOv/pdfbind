"""PDF rendering logic for combining PDFs with table of contents."""

from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field, PositiveInt, RootModel, ValidationError

from tunery.composer import Composer
from tunery.library import (
    LibraryCollection,
    LibraryRecord,
    load_project_libraries,
)


class FileEntry(BaseModel):
    """A file entry specifying a PDF source and optional page range/notes.

    Either 'file' or 'title' must be provided. If only 'title' is provided,
    the file will be looked up in configured libraries.
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


class Layout(RootModel[List[ConfigEntry | SectionEntry | FileEntry]]):
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
    libraries: LibraryCollection | None = None,
) -> ProcessEntryResult:
    """
    Add the requested pages for an entry to the combined PDF.

    Returns: SuccessResult on success, NotFoundResult if title not found
             (both subclasses of ProcessEntryResult).
    """
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
            return NotFoundResult(title=title)

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

    layout_entries: list[SectionEntry | FileEntry] = []
    for record in layout.root:
        if isinstance(record, ConfigEntry):
            for library_record in record.config:
                libraries.add(library_record.load(layout_path.parent))
        else:
            layout_entries.append(record)

    default_dir = layout_path.parent.resolve()

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
                    libraries,
                )
                print(result.format())

    with Composer(output, autosave=False) as composer:
        process_items(layout_entries)
        composer.save()


def lookup_and_extract(
    title: str,
    output: Path | None,
) -> None:
    """
    Look up a title in configured libraries and extract it to PDF.

    Args:
        title: The title to search for.
        output: Output path - if file, use as-is; if directory, save <title>.pdf there;
                if None, save <title>.pdf in current directory.
    """
    libraries = load_project_libraries()
    library_match = libraries.lookup_title(title)
    if library_match is None:
        print(f'No matches found for "{title}"')
        return

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
