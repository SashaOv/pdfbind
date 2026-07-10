from pathlib import Path

from tunery import main as cli


def test_render_command_uses_default_output(monkeypatch) -> None:
    calls = []

    def render(layout: Path, output: Path):
        calls.append((layout, output))

    monkeypatch.setattr(cli, "render", render)

    cli.main(["render", "setlists/favorites.yaml"])

    assert calls == [
        (
            Path("setlists/favorites.yaml"),
            Path("setlists/favorites.pdf"),
        )
    ]


def test_render_command_accepts_options(monkeypatch) -> None:
    calls = []

    def render(layout: Path, output: Path):
        calls.append((layout, output))

    monkeypatch.setattr(cli, "render", render)

    cli.main(
        [
            "render",
            "favorites.yaml",
            "-o",
            "book.pdf",
        ]
    )

    assert calls == [
        (
            Path("favorites.yaml"),
            Path("book.pdf"),
        )
    ]


def test_lookup_command_accepts_options(monkeypatch) -> None:
    calls = []

    def lookup_and_extract(title: str, output: Path | None):
        calls.append((title, output))

    import tunery.render

    monkeypatch.setattr(tunery.render, "lookup_and_extract", lookup_and_extract)

    cli.main(["lookup", "Blue Monk", "-o", "blue.pdf"])

    assert calls == [("Blue Monk", Path("blue.pdf"))]


def test_lookup_command_accepts_multiple_titles(monkeypatch) -> None:
    calls = []

    def lookup_and_extract(title: str, output: Path | None):
        calls.append((title, output))

    import tunery.render

    monkeypatch.setattr(tunery.render, "lookup_and_extract", lookup_and_extract)

    cli.main(["lookup", "Blue Monk", "Autumn Leaves"])

    assert calls == [
        ("Blue Monk", None),
        ("Autumn Leaves", None),
    ]
