import json
from pathlib import Path

import pikepdf
import pytest

from tunery.library import (
    DirectoryLibrary,
    IndexedPdfLibrary,
    LibraryCollection,
    LibraryRecord,
    find_project_config,
    load_project_libraries,
)
from tunery.render import lookup_and_extract


def create_pdf(path: Path, page_count: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for _ in range(page_count):
        pdf.add_blank_page(page_size=(100, 100))
    pdf.save(path)
    pdf.close()
    return path


def test_find_project_config_searches_at_most_eight_parents(tmp_path: Path) -> None:
    config = tmp_path / "tunery.yaml"
    config.write_text("[]\n")
    within_limit = tmp_path.joinpath(*[f"level-{i}" for i in range(8)])
    within_limit.mkdir(parents=True)
    beyond_limit = within_limit / "level-8"
    beyond_limit.mkdir()

    assert find_project_config(within_limit) == config
    assert find_project_config(beyond_limit) is None


def test_load_project_libraries_defaults_to_current_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    libraries = load_project_libraries(tmp_path)

    assert libraries.directories == [tmp_path]
    assert "Project configuration was not found, using defaults" in capsys.readouterr().out


def test_load_project_libraries_resolves_records_from_config_directory(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    chart = create_pdf(project_dir / "charts" / "Blue Monk.pdf")
    project_dir.joinpath("tunery.yaml").write_text(
        "- library: charts\n  match: exact\n"
    )
    working_dir = project_dir / "setlists"
    working_dir.mkdir()

    libraries = load_project_libraries(working_dir)

    assert libraries.lookup_title("Blue Monk").source == chart


def test_lookup_extracts_from_discovered_directory_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chart = create_pdf(tmp_path / "charts" / "Blue Monk.pdf", 2)
    tmp_path.joinpath("tunery.yaml").write_text(
        "- library: charts\n  match: exact\n"
    )
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "result.pdf"

    lookup_and_extract("Blue Monk", output)

    assert chart.exists()
    with pikepdf.Pdf.open(output) as pdf:
        assert len(pdf.pages) == 2


def test_directory_library_honors_exact_and_fuzzy_matching(tmp_path: Path) -> None:
    chart = create_pdf(tmp_path / "Autumn Leaves.pdf")

    exact = DirectoryLibrary(tmp_path, match="exact")
    fuzzy = DirectoryLibrary(tmp_path, match="fuzzy")

    assert exact.lookup_title("autumn leaves").source == chart
    assert exact.lookup_title("Autum Leaves") is None
    assert fuzzy.lookup_title("Autum Leaves").source == chart


def test_library_collection_gives_later_libraries_priority(tmp_path: Path) -> None:
    first = create_pdf(tmp_path / "first" / "Blue Monk.pdf", 1)
    second = create_pdf(tmp_path / "second" / "Blue Monk.pdf", 2)
    libraries = LibraryCollection(
        [
            DirectoryLibrary(first.parent, match="exact"),
            DirectoryLibrary(second.parent, match="exact"),
        ]
    )

    assert libraries.lookup_title("Blue Monk").source == second


def test_library_collection_prioritizes_later_directory_over_indexed_pdf(
    tmp_path: Path,
) -> None:
    book = create_pdf(tmp_path / "book.pdf", 3)
    index_path = tmp_path / "book.json"
    index_path.write_text(
        json.dumps([{"title": "Blue Monk", "page": 2}])
    )
    handout = create_pdf(tmp_path / "handouts" / "Blue Monk.pdf")
    libraries = LibraryCollection(
        [
            IndexedPdfLibrary.from_json(index_path, book),
            DirectoryLibrary(handout.parent),
        ]
    )

    result = libraries.lookup_title("Blue Monk")

    assert result is not None
    assert result.source == handout
    assert result.source != book


def test_indexed_library_record_requires_source(tmp_path: Path) -> None:
    index_path = tmp_path / "book.json"
    index_path.write_text("[]")

    with pytest.raises(ValueError, match="requires source"):
        LibraryRecord(library=str(index_path)).load(tmp_path)


def test_indexed_library_record_resolves_source_and_applies_shift(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    source = create_pdf(project_dir / "books" / "Real Book.pdf", 50)
    index_path = project_dir / "indexes" / "real-book.json"
    index_path.parent.mkdir()
    index_path.write_text(
        json.dumps([{"title": "Autumn Leaves", "page": 39, "pages": 2}])
    )

    library = LibraryRecord(
        library="indexes/real-book.json",
        source="books/Real Book.pdf",
        shift=2,
    ).load(project_dir)
    result = library.lookup_title("autumn leaves")

    assert result is not None
    assert result.source == source
    assert result.page == 41
    assert result.length == 2
    assert library.lookup_file("Real Book.pdf") is None


def test_indexed_pdf_library_defaults_shift_to_zero(tmp_path: Path) -> None:
    source = create_pdf(tmp_path / "books" / "Real Book.pdf", 50)
    index_path = tmp_path / "indexes" / "real-book.json"
    index_path.parent.mkdir()
    index_path.write_text(
        json.dumps([{"title": "Autumn Leaves", "page": 39, "pages": 2}])
    )

    library = IndexedPdfLibrary.from_json(index_path, source, match="exact")
    result = library.lookup_title("autumn leaves")

    assert result is not None
    assert result.source == source
    assert result.page == 39
    assert result.length == 2


def test_indexed_pdf_library_honors_fuzzy_matching(tmp_path: Path) -> None:
    source = create_pdf(tmp_path / "book.pdf", 2)
    index_path = tmp_path / "book.json"
    index_path.write_text(
        json.dumps([{"title": "Autumn Leaves", "page": 1}])
    )

    exact = IndexedPdfLibrary.from_json(index_path, source, match="exact")
    fuzzy = IndexedPdfLibrary.from_json(index_path, source, match="fuzzy")

    assert exact.lookup_title("Autum Leaves") is None
    assert fuzzy.lookup_title("Autum Leaves").title == "Autumn Leaves"


@pytest.mark.parametrize(
    ("contents", "create_source", "message"),
    [
        ("not json", True, "Invalid indexed PDF library"),
        ("{}", True, "Invalid indexed PDF library"),
        ("[]", False, "Source PDF not found"),
    ],
)
def test_indexed_pdf_library_reports_invalid_inputs(
    tmp_path: Path, contents: str, create_source: bool, message: str
) -> None:
    index_path = tmp_path / "book.json"
    index_path.write_text(contents)
    source = tmp_path / "book.pdf"
    if create_source:
        create_pdf(source)

    with pytest.raises(ValueError, match=message):
        IndexedPdfLibrary.from_json(index_path, source)


@pytest.mark.parametrize(
    ("record_data", "field"),
    [
        ({"source": "book.pdf"}, "source"),
        ({"source": None}, "source"),
        ({"shift": 0}, "shift"),
    ],
)
def test_directory_library_rejects_indexed_fields(
    tmp_path: Path, record_data: dict[str, object], field: str
) -> None:
    library_dir = tmp_path / "charts"
    library_dir.mkdir()

    with pytest.raises(ValueError, match=field):
        LibraryRecord(library="charts", **record_data).load(tmp_path)


def test_indexed_library_rejects_non_pdf_source(tmp_path: Path) -> None:
    index_path = tmp_path / "book.json"
    index_path.write_text("[]")
    source = tmp_path / "book.txt"
    source.write_text("not a PDF")

    with pytest.raises(ValueError, match="Source must be a PDF"):
        LibraryRecord(library="book.json", source="book.txt").load(tmp_path)


def test_indexed_library_rejects_nonpositive_shifted_page(tmp_path: Path) -> None:
    index_path = tmp_path / "book.json"
    index_path.write_text(json.dumps([{"title": "Blue Monk", "page": 1}]))
    create_pdf(tmp_path / "book.pdf")

    with pytest.raises(ValueError, match="must be positive"):
        LibraryRecord(
            library="book.json",
            source="book.pdf",
            shift=-1,
        ).load(tmp_path)


def test_yaml_collection_loads_multiple_libraries_with_relative_paths(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "rb-index"
    source_a = create_pdf(shared / "Books" / "A.pdf", 3)
    (shared / "Bob.json").write_text(
        json.dumps([{"title": "Tune A", "page": 2}])
    )
    handout = create_pdf(shared / "handouts" / "Tune B.pdf")
    (shared / "tunery.yaml").write_text(
        "- library: Bob.json\n"
        "  source: Books/A.pdf\n"
        "- library: handouts\n"
    )
    project = tmp_path / "proj"
    project.mkdir()

    library = LibraryRecord(library=str(shared / "tunery.yaml")).load(project)

    result_a = library.lookup_title("Tune A")
    assert result_a is not None
    assert result_a.source == source_a
    assert result_a.page == 2
    result_b = library.lookup_title("Tune B")
    assert result_b is not None
    assert result_b.source == handout


def test_yaml_collection_match_applies_only_when_inner_unspecified(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared"
    create_pdf(shared / "explicit-exact" / "Autumn Leaves.pdf")
    create_pdf(shared / "defaulted-fuzzy" / "Autumn Leaves.pdf")
    (shared / "collection.yaml").write_text(
        "- library: explicit-exact\n"
        "  match: exact\n"
        "- library: defaulted-fuzzy\n"
    )

    library = LibraryRecord(
        library="collection.yaml", match="fuzzy"
    ).load(shared)

    # Inner record without match inherits outer fuzzy and matches the typo.
    assert library.lookup_title("Autum Leaves") is not None
    assert library.lookup_title("Autum Leaves").source.parent.name == "defaulted-fuzzy"

    # Inner record with explicit exact keeps exact mode despite outer fuzzy.
    explicit_only = tmp_path / "explicit.yaml"
    explicit_only.write_text("- library: shared/explicit-exact\n  match: exact\n")
    explicit_library = LibraryRecord(library="explicit.yaml", match="fuzzy").load(
        tmp_path
    )
    assert explicit_library.lookup_title("Autum Leaves") is None
    assert explicit_library.lookup_title("Autumn Leaves") is not None


def test_yaml_collection_supports_nested_includes(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    chart = create_pdf(shared / "charts" / "Blue Monk.pdf")
    (shared / "inner.yaml").write_text("- library: charts\n")
    (shared / "outer.yaml").write_text("- library: inner.yaml\n")

    library = LibraryRecord(library="outer.yaml").load(shared)

    assert library.lookup_title("Blue Monk").source == chart


def test_yaml_collection_rejects_source_and_shift(tmp_path: Path) -> None:
    collection = tmp_path / "collection.yaml"
    collection.write_text("- library: charts\n")
    (tmp_path / "charts").mkdir()

    with pytest.raises(ValueError, match="must not specify source"):
        LibraryRecord(library="collection.yaml", source="book.pdf").load(tmp_path)

    with pytest.raises(ValueError, match="must not specify shift"):
        LibraryRecord(library="collection.yaml", shift=1).load(tmp_path)


def test_yaml_collection_detects_circular_includes(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("- library: b.yaml\n")
    (tmp_path / "b.yaml").write_text("- library: a.yaml\n")

    with pytest.raises(ValueError, match="Circular"):
        LibraryRecord(library="a.yaml").load(tmp_path)


def test_yaml_collection_reports_invalid_contents(tmp_path: Path) -> None:
    collection = tmp_path / "collection.yaml"
    collection.write_text("not a list\n")

    with pytest.raises(ValueError, match="Invalid library collection"):
        LibraryRecord(library=str(collection)).load(tmp_path)
