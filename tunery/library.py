import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel, PositiveInt, TypeAdapter, ValidationError

from tunery.fuzzy_index import FuzzyIndex, normalize_key


MatchMode = Literal["exact", "fuzzy"]
PROJECT_CONFIG_NAME = "tunery.yaml"
PROJECT_CONFIG_PARENT_LIMIT = 8


@dataclass(frozen=True)
class LibraryMatch:
    title: str
    source: Path
    page: int | None = None
    length: int | None = None
    score: float | None = None


class Library(Protocol):
    def lookup_title(self, title: str) -> LibraryMatch | None: ...

    def lookup_file(self, file: str) -> LibraryMatch | None: ...


class DirectoryLibrary:
    def __init__(self, path: Path, *, match: MatchMode = "exact") -> None:
        self.path = path.resolve()
        self.match = match
        if not self.path.is_dir():
            raise ValueError(f"Library directory not found: {self.path}")

        self._title_index = FuzzyIndex[Path]()
        self._file_index = FuzzyIndex[Path]()
        self._titles: dict[str, Path] = {}
        self._files: dict[str, Path] = {}
        for pdf_path in sorted(self.path.glob("*.pdf")):
            self._title_index.add(pdf_path.stem, pdf_path)
            self._file_index.add(pdf_path.name, pdf_path)
            self._titles.setdefault(normalize_key(pdf_path.stem), pdf_path)
            self._files.setdefault(normalize_key(pdf_path.name), pdf_path)

    def lookup_title(self, title: str) -> LibraryMatch | None:
        return self._lookup(title, self._titles, self._title_index, use_stem=True)

    def lookup_file(self, file: str) -> LibraryMatch | None:
        path = Path(file)
        if path.is_absolute():
            return None
        candidate = (self.path / path).resolve()
        if (
            candidate.is_relative_to(self.path)
            and candidate.is_file()
            and candidate.suffix.lower() == ".pdf"
        ):
            return LibraryMatch(title=candidate.name, source=candidate)
        if path.parent != Path("."):
            return None
        return self._lookup(path.name, self._files, self._file_index, use_stem=False)

    def _lookup(
        self,
        query: str,
        exact_items: dict[str, Path],
        fuzzy_index: FuzzyIndex[Path],
        *,
        use_stem: bool,
    ) -> LibraryMatch | None:
        exact = exact_items.get(normalize_key(query))
        if exact is not None:
            return LibraryMatch(
                title=exact.stem if use_stem else exact.name,
                source=exact,
            )
        if self.match == "exact":
            return None

        matches = fuzzy_index.match(query, score_cutoff=90, limit=1)
        if not matches:
            return None
        result = matches[0]
        return LibraryMatch(
            title=result.item.stem if use_stem else result.item.name,
            source=result.item,
            score=result.score,
        )


class IndexedTune(BaseModel):
    title: str
    page: PositiveInt
    pages: PositiveInt = 1


INDEXED_TUNES_ADAPTER = TypeAdapter(list[IndexedTune])


class IndexedPdfLibrary:
    def __init__(
        self,
        index_path: Path,
        source: Path,
        tunes: list[IndexedTune],
        *,
        shift: int = 0,
        match: MatchMode = "exact",
    ) -> None:
        self.index_path = index_path.resolve()
        self.source = source.resolve()
        self.match = match
        self._tunes: dict[str, IndexedTune] = {}
        self._title_index = FuzzyIndex[IndexedTune]()
        self._shift = shift
        for tune in tunes:
            effective_page = tune.page + shift
            if effective_page < 1:
                raise ValueError(
                    f'Invalid page for "{tune.title}" in {self.index_path}: '
                    f"{tune.page} + shift {shift} must be positive"
                )
            self._tunes.setdefault(normalize_key(tune.title), tune)
            self._title_index.add(tune.title, tune)

    @classmethod
    def from_json(
        cls,
        index_path: Path,
        source: Path,
        *,
        shift: int = 0,
        match: MatchMode = "exact",
    ) -> "IndexedPdfLibrary":
        resolved_index = index_path.resolve()
        try:
            raw_data = json.loads(resolved_index.read_text(encoding="utf-8"))
            tunes = INDEXED_TUNES_ADAPTER.validate_python(raw_data)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise ValueError(
                f"Invalid indexed PDF library {resolved_index}: {error}"
            ) from error

        resolved_source = source.resolve()
        if not resolved_source.is_file():
            raise ValueError(
                f"Source PDF not found: {resolved_source} "
                f"(configured for {resolved_index})"
            )
        if resolved_source.suffix.lower() != ".pdf":
            raise ValueError(
                f"Source must be a PDF: {resolved_source} "
                f"(configured for {resolved_index})"
            )
        return cls(
            resolved_index,
            resolved_source,
            tunes,
            shift=shift,
            match=match,
        )

    def lookup_title(self, title: str) -> LibraryMatch | None:
        tune = self._tunes.get(normalize_key(title))
        score: float | None = None
        if tune is None and self.match == "fuzzy":
            matches = self._title_index.match(title, score_cutoff=90, limit=1)
            if matches:
                tune = matches[0].item
                score = matches[0].score
        if tune is None:
            return None
        return LibraryMatch(
            title=tune.title,
            source=self.source,
            page=tune.page + self._shift,
            length=tune.pages,
            score=score,
        )

    def lookup_file(self, file: str) -> LibraryMatch | None:
        return None


class LibraryCollection:
    def __init__(self, libraries: list[Library] | None = None) -> None:
        self._libraries = list(libraries or [])

    @property
    def directories(self) -> list[Path]:
        result: list[Path] = []
        for library in self._libraries:
            if isinstance(library, DirectoryLibrary):
                result.append(library.path)
            elif isinstance(library, LibraryCollection):
                result.extend(library.directories)
        return result

    def add(self, library: Library) -> None:
        self._libraries.append(library)

    def lookup_title(self, title: str) -> LibraryMatch | None:
        for library in reversed(self._libraries):
            result = library.lookup_title(title)
            if result is not None:
                return result
        return None

    def lookup_file(self, file: str) -> LibraryMatch | None:
        for library in reversed(self._libraries):
            result = library.lookup_file(file)
            if result is not None:
                return result
        return None


class LibraryRecord(BaseModel):
    library: str
    source: str | None = None
    shift: int | None = None
    match: MatchMode = "exact"

    def _load_collection(self, path: Path, seen: tuple[Path, ...]) -> Library:
        if "source" in self.model_fields_set:
            raise ValueError(f"Library collection {path} must not specify source")
        if "shift" in self.model_fields_set:
            raise ValueError(f"Library collection {path} must not specify shift")
        if path in seen:
            chain = " -> ".join(str(p) for p in (*seen, path))
            raise ValueError(f"Circular library collection include: {chain}")
        try:
            raw_collection = yaml.safe_load(path.read_text(encoding="utf-8"))
            records = [
                LibraryRecord.model_validate(item) for item in (raw_collection or [])
            ]
        except (OSError, yaml.YAMLError, ValidationError, TypeError) as error:
            raise ValueError(
                f"Invalid library collection {path}: {error}"
            ) from error
        if "match" in self.model_fields_set:
            records = [
                record
                if "match" in record.model_fields_set
                else record.model_copy(update={"match": self.match})
                for record in records
            ]
        seen = (*seen, path)
        return LibraryCollection(
            [record.load(path.parent, seen) for record in records]
        )

    def load(self, base_dir: Path, _seen: tuple[Path, ...] = ()) -> Library:
        path = Path(self.library)
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        else:
            path = path.resolve()
        if path.suffix.lower() in (".yaml", ".yml") and path.is_file():
            return self._load_collection(path, _seen)
        if path.is_dir():
            if "source" in self.model_fields_set:
                raise ValueError(
                    f"Directory library {path} must not specify source"
                )
            if "shift" in self.model_fields_set:
                raise ValueError(f"Directory library {path} must not specify shift")
            return DirectoryLibrary(path, match=self.match)
        if path.suffix.lower() == ".json" and path.is_file():
            if self.source is None:
                raise ValueError(f"Indexed PDF library {path} requires source")
            source = Path(self.source)
            if not source.is_absolute():
                source = (base_dir / source).resolve()
            shift = 0 if self.shift is None else self.shift
            return IndexedPdfLibrary.from_json(
                path,
                source,
                shift=shift,
                match=self.match,
            )
        raise ValueError(
            f"Library path must be a directory, JSON file, or YAML file: {path}"
        )


def find_project_config(start_dir: Path) -> Path | None:
    directory = start_dir.resolve()
    for depth in range(PROJECT_CONFIG_PARENT_LIMIT + 1):
        candidate = directory / PROJECT_CONFIG_NAME
        if candidate.is_file():
            return candidate
        if depth == PROJECT_CONFIG_PARENT_LIMIT or directory.parent == directory:
            break
        directory = directory.parent
    return None


def load_library_records(
    records: list[LibraryRecord], base_dir: Path
) -> LibraryCollection:
    return LibraryCollection([record.load(base_dir) for record in records])


def load_project_libraries(start_dir: Path | None = None) -> LibraryCollection:
    start = (start_dir or Path.cwd()).resolve()
    config_path = find_project_config(start)
    if config_path is None:
        print("Project configuration was not found, using defaults")
        return LibraryCollection([DirectoryLibrary(start)])
    # Dereference symlinks so relative library/source paths resolve to real files.
    config_path = config_path.resolve()

    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        records = [LibraryRecord.model_validate(item) for item in (raw_config or [])]
    except (OSError, yaml.YAMLError, ValidationError, TypeError) as error:
        raise ValueError(f"Invalid project configuration {config_path}: {error}") from error
    return load_library_records(records, config_path.parent)
