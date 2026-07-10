from pathlib import Path

from tunery import main as cli


def test_index_command_builds_default_index(monkeypatch) -> None:
    calls = []

    def build(index_json: Path, output_path: Path):
        calls.append((index_json, output_path))

    monkeypatch.setattr(cli.Index, "build", build)

    cli.main(["index", "index.json"])

    assert calls == [(Path("index.json"), cli.DEFAULT_INDEX_PATH)]


def test_render_command_uses_default_output(monkeypatch) -> None:
    calls = []

    def render(layout: Path, output: Path, index_path: Path):
        calls.append((layout, output, index_path))

    monkeypatch.setattr(cli, "render", render)

    cli.main(["render", "setlists/favorites.yaml"])

    assert calls == [
        (
            Path("setlists/favorites.yaml"),
            Path("setlists/favorites.pdf"),
            cli.DEFAULT_INDEX_PATH,
        )
    ]


def test_render_command_accepts_options(monkeypatch) -> None:
    calls = []

    def render(layout: Path, output: Path, index_path: Path):
        calls.append((layout, output, index_path))

    monkeypatch.setattr(cli, "render", render)

    cli.main(
        [
            "render",
            "favorites.yaml",
            "-o",
            "book.pdf",
            "--index",
            "index.sqlite",
        ]
    )

    assert calls == [
        (
            Path("favorites.yaml"),
            Path("book.pdf"),
            Path("index.sqlite"),
        )
    ]


def test_lookup_command_accepts_options(monkeypatch) -> None:
    calls = []

    def lookup_and_extract(title: str, output: Path | None, index_path: Path):
        calls.append((title, output, index_path))

    import tunery.render

    monkeypatch.setattr(tunery.render, "lookup_and_extract", lookup_and_extract)

    cli.main(["lookup", "Blue Monk", "-o", "blue.pdf", "--index", "index.sqlite"])

    assert calls == [("Blue Monk", Path("blue.pdf"), Path("index.sqlite"))]


def test_lookup_command_accepts_multiple_titles(monkeypatch) -> None:
    calls = []

    def lookup_and_extract(title: str, output: Path | None, index_path: Path):
        calls.append((title, output, index_path))

    import tunery.render

    monkeypatch.setattr(tunery.render, "lookup_and_extract", lookup_and_extract)

    cli.main(["lookup", "Blue Monk", "Autumn Leaves", "--index", "index.sqlite"])

    assert calls == [
        ("Blue Monk", None, Path("index.sqlite")),
        ("Autumn Leaves", None, Path("index.sqlite")),
    ]
