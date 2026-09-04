import json
from pathlib import Path
from typing import Sequence

import pikepdf
import pytest
import yaml

from tunery.composer import copy_pages, get_page_label_to_index_map
from tunery.render import render


def create_pdf(path: Path, page_count: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for _ in range(page_count):
        pdf.add_blank_page(page_size=(100, 100))
    pdf.save(path)
    pdf.close()
    return path


def write_layout(path: Path, records: Sequence[dict]) -> Path:
    path.write_text(yaml.safe_dump(list(records), sort_keys=False))
    return path


def write_json(path: Path, data: object) -> Path:
    import json

    path.write_text(json.dumps(data))
    return path


def outline_page_index(pdf: pikepdf.Pdf, outline_item: pikepdf.OutlineItem) -> int:
    destination = outline_item.destination
    if destination is None:
        msg = f"Outline item '{outline_item.title}' is missing a destination"
        raise AssertionError(msg)
    return pdf.pages.index(destination[0])  # pyright: ignore


def test_render_resolves_title_and_file_through_layout_directory_library(
    tmp_path: Path,
) -> None:
    library_dir = tmp_path / "library"
    create_pdf(library_dir / "Autumn Leaves.pdf", 2)
    create_pdf(library_dir / "Special.pdf", 1)
    layout_path = tmp_path / "setlist" / "gig.yaml"
    layout_path.parent.mkdir(parents=True, exist_ok=True)
    layout_path = write_layout(
        layout_path,
        [
            {"config": [{"library": "../library", "match": "exact"}]},
            {"title": "Autumn Leaves"},
            {"file": "Special.pdf"},
        ],
    )
    output_path = tmp_path / "setbook.pdf"

    render(layout_path, output_path)

    with pikepdf.Pdf.open(output_path) as pdf:
        assert len(pdf.pages) == 3


def test_render_discovers_project_config_from_layout_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    chart = create_pdf(project_dir / "Repertoire" / "Bandstand Boogie-Lowden.pdf", 2)
    project_dir.joinpath("tunery.yaml").write_text(
        "- library: Repertoire\n  match: exact\n"
    )
    layout_dir = project_dir / "setlists" / "gig"
    layout_dir.mkdir(parents=True)
    layout_path = write_layout(
        layout_dir / "setlist.yaml",
        [{"file": "Bandstand Boogie-Lowden.pdf"}],
    )
    unrelated_cwd = tmp_path / "elsewhere"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    output_path = tmp_path / "setbook.pdf"

    render(layout_path, output_path)

    assert chart.exists()
    with pikepdf.Pdf.open(output_path) as pdf:
        assert len(pdf.pages) == 2


def test_render_extracts_pages_from_indexed_pdf_library(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    source = create_pdf(project_dir / "books" / "Real Book.pdf", 6)
    index_path = project_dir / "indexes" / "real-book.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text(
        json.dumps([{"title": "Autumn Leaves", "page": 3, "pages": 2}])
    )
    project_dir.joinpath("tunery.yaml").write_text(
        "- library: indexes/real-book.json\n"
        "  source: books/Real Book.pdf\n"
        "  match: exact\n"
    )
    layout_dir = project_dir / "setlists"
    layout_dir.mkdir()
    layout_path = write_layout(layout_dir / "gig.yaml", [{"title": "Autumn Leaves"}])
    output_path = tmp_path / "setbook.pdf"

    render(layout_path, output_path)

    assert source.exists()
    with pikepdf.Pdf.open(output_path) as pdf:
        assert len(pdf.pages) == 2


def test_render_loads_indexed_pdf_from_layout_config(tmp_path: Path) -> None:
    source = create_pdf(tmp_path / "books" / "Real Book.pdf", 4)
    index_path = tmp_path / "indexes" / "real-book.json"
    index_path.parent.mkdir()
    index_path.write_text(
        json.dumps([{"title": "Blue Monk", "page": 2}])
    )
    layout_dir = tmp_path / "setlists"
    layout_dir.mkdir()
    layout_path = write_layout(
        layout_dir / "gig.yaml",
        [
            {
                "config": [
                    {
                        "library": "../indexes/real-book.json",
                        "source": "../books/Real Book.pdf",
                    }
                ]
            },
            {"title": "Blue Monk"},
        ],
    )
    output_path = tmp_path / "setbook.pdf"

    render(layout_path, output_path)

    assert source.exists()
    with pikepdf.Pdf.open(output_path) as pdf:
        assert len(pdf.pages) == 1


def test_render_layout_library_match_mode_is_not_per_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_dir = tmp_path / "library"
    create_pdf(library_dir / "Autumn Leaves.pdf", 1)
    layout_dir = tmp_path / "setlist"
    layout_dir.mkdir()
    layout_path = write_layout(
        layout_dir / "gig.yaml",
        [
            {"config": [{"library": "../library", "match": "exact"}]},
            {"title": "Autum Leaves"},
        ],
    )
    output_path = tmp_path / "setbook.pdf"

    render(layout_path, output_path)

    assert 'not found "Autum Leaves"' in capsys.readouterr().out


def test_bind_pdf_combines_sections_and_flat_entries(tmp_path: Path) -> None:
    layout_dir = tmp_path / "setlist"
    layout_dir.mkdir()

    schedule_pdf = create_pdf(layout_dir / "Schedule.pdf", 2)
    create_pdf(layout_dir / "Songbook.pdf", 6)
    create_pdf(layout_dir / "Groove Standard.pdf", 1)
    create_pdf(layout_dir / "Ballad.pdf", 1)

    dropbox_dir = tmp_path / "absolute"
    feature_pdf = create_pdf(dropbox_dir / "Feature Piece.pdf", 1)
    duet_pdf = create_pdf(dropbox_dir / "Duet.pdf", 1)

    records = [
        {"file": str(schedule_pdf), "title": "Timeline"},
        {
            "section": "Set 1",
            "body": [
                {
                    "file": "Songbook.pdf",
                    "page": 1,
                    "title": "Opening Groove",
                },
                {
                    "file": "Songbook.pdf",
                    "page": 2,
                    "length": 2,
                    "title": "Latin Medley",
                },
                {
                    "file": "Groove Standard.pdf",
                    "title": "Groove Standard",
                },
            ],
        },
        {
            "section": "Set 1a (Feature Spotlight)",
            "body": [
                {
                    "file": str(feature_pdf),
                    "title": "Feature Piece",
                },
                {
                    "file": str(duet_pdf),
                    "title": "Duet",
                },
            ],
        },
        {"file": "Ballad.pdf", "title": "Ballad"},
    ]

    layout_path = write_layout(layout_dir / "25-11-09.yaml", records)
    output_path = layout_dir / "combined.pdf"

    render(layout_path, output_path)

    with pikepdf.Pdf.open(output_path) as merged:
        assert len(merged.pages) == 9

        with merged.open_outline() as outline:
            root_items = list(outline.root)
            assert [item.title for item in root_items] == [
                "Timeline",
                "Set 1",
                "Set 1a (Feature Spotlight)",
                "Ballad",
            ]

            set_one = root_items[1]
            set_one_children = list(set_one.children)
            assert [child.title for child in set_one_children] == [
                "Opening Groove",
                "Latin Medley",
                "Groove Standard",
            ]
            assert outline_page_index(merged, set_one) == 2
            assert [outline_page_index(merged, child) for child in set_one_children] == [
                2,
                3,
                5,
            ]

            set_one_a = root_items[2]
            set_one_a_children = list(set_one_a.children)
            assert [child.title for child in set_one_a_children] == [
                "Feature Piece",
                "Duet",
            ]
            assert outline_page_index(merged, set_one_a) == 6
            assert [outline_page_index(merged, child) for child in set_one_a_children] == [
                6,
                7,
            ]

            ballad_item = root_items[3]
            assert outline_page_index(merged, ballad_item) == 8


def test_bind_pdf_handles_empty_section(tmp_path: Path) -> None:
    layout_dir = tmp_path / "empty"
    layout_dir.mkdir()

    create_pdf(layout_dir / "Solo Tune.pdf", 1)

    records = [
        {"section": "Empty Section", "body": []},
        {"file": "Solo Tune.pdf", "title": "Solo Tune"},
    ]

    layout_path = write_layout(layout_dir / "empty.yaml", records)
    output_path = layout_dir / "empty.pdf"

    render(layout_path, output_path)

    with pikepdf.Pdf.open(output_path) as merged:
        assert len(merged.pages) == 1

        with merged.open_outline() as outline:
            root_items = list(outline.root)
            assert root_items[0].title == "Empty Section"
            assert outline_page_index(merged, root_items[0]) == 0
            assert list(root_items[0].children) == []
            assert root_items[1].title == "Solo Tune"
            assert outline_page_index(merged, root_items[1]) == 0


def test_render_prefers_layout_library_over_index(tmp_path: Path) -> None:
    layout_dir = tmp_path / "setlist"
    layout_dir.mkdir()

    create_pdf(layout_dir / "Country.pdf", 1)
    create_pdf(tmp_path / "books" / "RealBook.pdf", 3)
    write_json(
        tmp_path / "book.json",
        [{"title": "Country", "page": 2, "pages": 2}],
    )
    tmp_path.joinpath("tunery.yaml").write_text(
        "- library: book.json\n  source: books/RealBook.pdf\n"
    )

    layout_path = write_layout(
        layout_dir / "combo.yaml",
        [
            {"config": [{"library": ".", "match": "exact"}]},
            {"title": "Country"},
        ],
    )
    output_path = layout_dir / "combined.pdf"

    render(layout_path, output_path)

    with pikepdf.Pdf.open(output_path) as merged:
        assert len(merged.pages) == 1


def test_render_later_layout_library_takes_priority_over_index(tmp_path: Path) -> None:
    layout_dir = tmp_path / "setlist"
    layout_dir.mkdir()

    handouts_dir = tmp_path / "handouts"
    handouts_dir.mkdir()
    create_pdf(handouts_dir / "Country.pdf", 1)
    create_pdf(tmp_path / "books" / "RealBook.pdf", 3)
    write_json(
        tmp_path / "book.json",
        [{"title": "Country", "page": 2, "pages": 2}],
    )
    tmp_path.joinpath("tunery.yaml").write_text(
        "- library: book.json\n  source: books/RealBook.pdf\n"
    )

    layout_path = write_layout(
        layout_dir / "combo.yaml",
        [
            {"config": [{"library": "../handouts", "match": "exact"}]},
            {"title": "Country"},
        ],
    )
    output_path = layout_dir / "combined.pdf"

    render(layout_path, output_path)

    with pikepdf.Pdf.open(output_path) as merged:
        assert len(merged.pages) == 1


def test_render_directory_library_defaults_to_full_pdf(tmp_path: Path) -> None:
    layout_dir = tmp_path / "setlist"
    layout_dir.mkdir()

    create_pdf(layout_dir / "Country.pdf", 9)
    create_pdf(tmp_path / "books" / "RealBook.pdf", 3)
    write_json(
        tmp_path / "book.json",
        [{"title": "Country", "page": 2, "pages": 2}],
    )
    tmp_path.joinpath("tunery.yaml").write_text(
        "- library: book.json\n  source: books/RealBook.pdf\n"
    )

    layout_path = write_layout(
        layout_dir / "combo.yaml",
        [
            {"config": [{"library": ".", "match": "exact"}]},
            {"title": "Country"},
        ],
    )
    output_path = layout_dir / "combined.pdf"

    render(layout_path, output_path)

    with pikepdf.Pdf.open(output_path) as merged:
        assert len(merged.pages) == 9


def test_render_rejects_legacy_override_record(tmp_path: Path) -> None:
    layout_path = write_layout(tmp_path / "setlist.yaml", [{"override": "."}])

    with pytest.raises(ValueError, match="Validation error"):
        render(layout_path, tmp_path / "combined.pdf")


def test_copy_pages_validates_ranges(tmp_path: Path) -> None:
    source_pdf = create_pdf(tmp_path / "source.pdf", 2)
    combined_pdf = pikepdf.Pdf.new()

    with pytest.raises(ValueError):
        copy_pages(combined_pdf, str(source_pdf), start_page=3)

    with pytest.raises(ValueError):
        copy_pages(combined_pdf, str(source_pdf), start_page=2, length=3)


def test_get_page_label_to_index_map_handles_missing_labels(tmp_path: Path) -> None:
    """Test that page label mapping works for PDFs without page labels."""
    pdf_path = create_pdf(tmp_path / "test.pdf", 5)
    
    with pikepdf.Pdf.open(pdf_path) as pdf:
        label_map = get_page_label_to_index_map(pdf)
        
        # Should create 1:1 mapping (page 1 = index 0, page 2 = index 1, etc.)
        assert label_map == {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}


def test_get_page_label_to_index_map_handles_custom_labels(tmp_path: Path) -> None:
    """Test that page label mapping works for PDFs with custom page labels."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a PDF with custom page labels (e.g., starting at page 10)
    pdf = pikepdf.Pdf.new()
    for _ in range(5):
        pdf.add_blank_page(page_size=(100, 100))
    
    # Add page labels starting from 10
    page_labels = pikepdf.Dictionary(
        Nums=pikepdf.Array([
            0,  # Start at physical page 0
            pikepdf.Dictionary(St=10),  # Start numbering at 10
        ])
    )
    pdf.Root.PageLabels = page_labels
    pdf.save(pdf_path)
    pdf.close()
    
    with pikepdf.Pdf.open(pdf_path) as pdf:
        label_map = get_page_label_to_index_map(pdf)
        
        # Should map page label 10 to index 0, 11 to index 1, etc.
        assert label_map[10] == 0
        assert label_map[11] == 1
        assert label_map[12] == 2
        assert label_map[13] == 3
        assert label_map[14] == 4


def test_get_page_label_to_index_map_handles_malformed_labels(tmp_path: Path) -> None:
    """Test that page label mapping gracefully handles malformed page label structures."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a PDF with malformed page labels
    pdf = pikepdf.Pdf.new()
    for _ in range(3):
        pdf.add_blank_page(page_size=(100, 100))
    
    # Add malformed page labels (e.g., /S is a name instead of dict)
    page_labels = pikepdf.Dictionary(
        Nums=pikepdf.Array([
            0,
            pikepdf.Dictionary(S=pikepdf.Name.D),  # /S is a name, not a dict
        ])
    )
    pdf.Root.PageLabels = page_labels
    pdf.save(pdf_path)
    pdf.close()
    
    with pikepdf.Pdf.open(pdf_path) as pdf:
        label_map = get_page_label_to_index_map(pdf)
        
        # Should fall back to 1:1 mapping when labels are malformed
        assert label_map == {1: 0, 2: 1, 3: 2}


def test_get_page_label_to_index_map_handles_multiple_decimal_ranges(tmp_path: Path) -> None:
    """Test that page label mapping correctly handles multiple decimal ranges, preferring longer ranges."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a PDF similar to "The new real book vol 2.pdf" structure
    pdf = pikepdf.Pdf.new()
    for _ in range(20):
        pdf.add_blank_page(page_size=(100, 100))
    
    # Add page labels with multiple decimal ranges:
    # - Index 0: decimal starting at 1 (short range, 1 page)
    # - Index 1-3: alphabetic (should be skipped)
    # - Index 4-18: decimal starting at 1 (long range, main content)
    # - Index 19: decimal starting at 2 (short range, 1 page)
    page_labels = pikepdf.Dictionary(
        Nums=pikepdf.Array([
            0,
            pikepdf.Dictionary(S=pikepdf.Name.D),  # Decimal, defaults to start=1
            1,
            pikepdf.Dictionary(S=pikepdf.Name.a),  # Alphabetic, should be skipped
            4,
            pikepdf.Dictionary(S=pikepdf.Name.D),  # Decimal, defaults to start=1 (main range)
            19,
            pikepdf.Dictionary(S=pikepdf.Name.D, St=2),  # Decimal starting at 2
        ])
    )
    pdf.Root.PageLabels = page_labels
    pdf.save(pdf_path)
    pdf.close()
    
    with pikepdf.Pdf.open(pdf_path) as pdf:
        label_map = get_page_label_to_index_map(pdf)
        
        # Page 1 should map to index 4 (longer range), not index 0
        assert label_map[1] == 4
        # Page 2 should map to index 5 (longer range), not index 19
        assert label_map[2] == 5
        # Page 15 should map to index 18 (from the main range)
        assert label_map[15] == 18


def test_bind_pdf_handles_nested_sections(tmp_path: Path) -> None:
    """Test that nested sections (subsections) are supported in layout files."""
    layout_dir = tmp_path / "setlist"
    layout_dir.mkdir()

    create_pdf(layout_dir / "Opener.pdf", 1)
    create_pdf(layout_dir / "Song A.pdf", 1)
    create_pdf(layout_dir / "Song B.pdf", 1)
    create_pdf(layout_dir / "Closer.pdf", 1)

    # Layout with nested sections: Set 1 contains a subsection "Medley"
    records = [
        {"file": "Opener.pdf", "title": "Opener"},
        {
            "section": "Set 1",
            "body": [
                {"file": "Song A.pdf", "title": "Song A"},
                {
                    "section": "Medley",
                    "body": [
                        {"file": "Song B.pdf", "title": "Song B"},
                    ],
                },
            ],
        },
        {"file": "Closer.pdf", "title": "Closer"},
    ]

    layout_path = write_layout(layout_dir / "nested.yaml", records)
    output_path = layout_dir / "nested.pdf"

    render(layout_path, output_path)

    with pikepdf.Pdf.open(output_path) as merged:
        # Should have 4 pages total
        assert len(merged.pages) == 4

        with merged.open_outline() as outline:
            root_items = list(outline.root)
            # Top level: Opener, Set 1, Closer
            assert len(root_items) == 3
            assert root_items[0].title == "Opener"
            assert root_items[1].title == "Set 1"
            assert root_items[2].title == "Closer"

            # Set 1 children: Song A, Medley (subsection)
            set1_children = list(root_items[1].children)
            assert len(set1_children) == 2
            assert set1_children[0].title == "Song A"
            assert set1_children[1].title == "Medley"

            # Medley children: Song B
            medley_children = list(set1_children[1].children)
            assert len(medley_children) == 1
            assert medley_children[0].title == "Song B"


def test_process_file_entry_returns_not_found_result(tmp_path: Path) -> None:
    """Test that process_file_entry returns NotFoundResult for missing titles."""
    from tunery.composer import Composer
    from tunery.render import process_file_entry, FileEntry, NotFoundResult

    layout_dir = tmp_path / "setlist"
    layout_dir.mkdir()

    # Create a FileEntry for a title that doesn't exist
    entry = FileEntry(title="Missing Song")
    composer = Composer(tmp_path / "combined.pdf", autosave=False)

    result = process_file_entry(
        entry,
        default_dir=layout_dir,
        composer=composer,
    )
    composer.close()

    # Should return NotFoundResult
    assert isinstance(result, NotFoundResult)
    assert result.title == "Missing Song"
    assert 'not found "Missing Song"' in result.format()


def test_lookup_and_extract_single_match(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tunery.render import lookup_and_extract

    create_pdf(tmp_path / "books" / "RealBook.pdf", 5)
    write_json(
        tmp_path / "book.json",
        [
            {"title": "Autumn Leaves", "page": 2, "pages": 2},
            {"title": "Blue In Green", "page": 4},
        ],
    )
    tmp_path.joinpath("tunery.yaml").write_text(
        "- library: book.json\n  source: books/RealBook.pdf\n"
    )
    monkeypatch.chdir(tmp_path)

    output_path = tmp_path / "output.pdf"
    lookup_and_extract("Autumn Leaves", output_path)

    captured = capsys.readouterr()
    assert 'Found "Autumn Leaves"' in captured.out
    assert "Extracted to:" in captured.out

    assert output_path.exists()
    with pikepdf.Pdf.open(output_path) as pdf:
        assert len(pdf.pages) == 2


def test_lookup_and_extract_no_matches(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tunery.render import lookup_and_extract

    create_pdf(tmp_path / "books" / "RealBook.pdf", 3)
    write_json(
        tmp_path / "book.json",
        [{"title": "Autumn Leaves", "page": 1}],
    )
    tmp_path.joinpath("tunery.yaml").write_text(
        "- library: book.json\n  source: books/RealBook.pdf\n"
    )
    monkeypatch.chdir(tmp_path)

    output_path = tmp_path / "output.pdf"
    lookup_and_extract("Nonexistent Song", output_path)

    captured = capsys.readouterr()
    assert 'No matches found for "Nonexistent Song"' in captured.out
    assert not output_path.exists()


def test_lookup_and_extract_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tunery.render import lookup_and_extract

    create_pdf(tmp_path / "books" / "RealBook.pdf", 3)
    write_json(
        tmp_path / "book.json",
        [{"title": "Autumn Leaves", "page": 1, "pages": 2}],
    )
    tmp_path.joinpath("tunery.yaml").write_text(
        "- library: book.json\n  source: books/RealBook.pdf\n"
    )
    monkeypatch.chdir(tmp_path)

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    lookup_and_extract("Autumn Leaves", output_dir)

    expected_path = output_dir / "Autumn Leaves.pdf"
    assert expected_path.exists()
    with pikepdf.Pdf.open(expected_path) as pdf:
        assert len(pdf.pages) == 2


def test_render_resolves_relative_file_through_symlinked_parent(
    tmp_path: Path,
) -> None:
    """Relative file refs resolve lexically when the layout dir is symlinked."""
    real_gdrive = tmp_path / "real-gdrive"
    gig_dir = real_gdrive / "Shows" / "gig"
    gig_dir.mkdir(parents=True)
    create_pdf(tmp_path / "project" / "Vault" / "chart.pdf", 1)
    linked_gdrive = tmp_path / "project" / "GDrive"
    linked_gdrive.parent.mkdir(parents=True, exist_ok=True)
    linked_gdrive.symlink_to(real_gdrive, target_is_directory=True)
    layout_path = write_layout(
        linked_gdrive / "Shows" / "gig" / "gig.yaml",
        [{"file": "../../../Vault/chart.pdf"}],
    )
    output_path = tmp_path / "setbook.pdf"

    render(layout_path, output_path)

    with pikepdf.Pdf.open(output_path) as pdf:
        assert len(pdf.pages) == 1
