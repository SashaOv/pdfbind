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

    lookup_and_extract("Blue Monk", output, tmp_path / "missing.sqlite")

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
        json.dumps(
            {
                "source": "book.pdf",
                "tunes": [{"title": "Blue Monk", "page": 2}],
            }
        )
    )
    handout = create_pdf(tmp_path / "handouts" / "Blue Monk.pdf")
    libraries = LibraryCollection(
        [
            IndexedPdfLibrary.from_json(index_path),
            DirectoryLibrary(handout.parent),
        ]
    )

    result = libraries.lookup_title("Blue Monk")

    assert result is not None
    assert result.source == handout
    assert result.source != book


def test_library_record_rejects_non_directory_in_build_one(tmp_path: Path) -> None:
    index_path = tmp_path / "book.json"
    index_path.write_text("{}")

    with pytest.raises(ValueError, match="Invalid indexed PDF library"):
        LibraryRecord(library=str(index_path)).load(tmp_path)


def test_indexed_pdf_library_loads_page_ranges_and_shift(tmp_path: Path) -> None:
    source = create_pdf(tmp_path / "books" / "Real Book.pdf", 50)
    index_path = tmp_path / "indexes" / "real-book.json"
    index_path.parent.mkdir()
    index_path.write_text(
        json.dumps(
            {
                "source": "../books/Real Book.pdf",
                "shift": 2,
                "tunes": [
                    {"title": "Autumn Leaves", "page": 39, "pages": 2},
                ],
            }
        )
    )

    library = IndexedPdfLibrary.from_json(index_path, match="exact")
    result = library.lookup_title("autumn leaves")

    assert result is not None
    assert result.source == source
    assert result.page == 41
    assert result.length == 2
    assert library.lookup_file("Real Book.pdf") is None


def test_indexed_pdf_library_honors_fuzzy_matching(tmp_path: Path) -> None:
    create_pdf(tmp_path / "book.pdf", 2)
    index_path = tmp_path / "book.json"
    index_path.write_text(
        json.dumps(
            {
                "source": "book.pdf",
                "tunes": [{"title": "Autumn Leaves", "page": 1}],
            }
        )
    )

    exact = IndexedPdfLibrary.from_json(index_path, match="exact")
    fuzzy = IndexedPdfLibrary.from_json(index_path, match="fuzzy")

    assert exact.lookup_title("Autum Leaves") is None
    assert fuzzy.lookup_title("Autum Leaves").title == "Autumn Leaves"


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("not json", "Invalid indexed PDF library"),
        (json.dumps({"source": "missing.pdf", "tunes": []}), "Source PDF not found"),
    ],
)
def test_indexed_pdf_library_reports_invalid_inputs(
    tmp_path: Path, contents: str, message: str
) -> None:
    index_path = tmp_path / "book.json"
    index_path.write_text(contents)

    with pytest.raises(ValueError, match=message):
        IndexedPdfLibrary.from_json(index_path)
