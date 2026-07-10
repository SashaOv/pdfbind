"""Tunery CLI - Build PDF setbooks from sheet music collections."""

from pathlib import Path
from typing import Annotated, Sequence

from cyclopts import App, Parameter

import tunery.render as render_module
from tunery.index import Index
from tunery.render import render

DEFAULT_INDEX_PATH = Path.home() / ".cache" / "tunery" / "index.sqlite"
app = App(help="Tunery: Build PDF setbooks from sheet music collections")


@app.command(name="index")
def build_index(
    index_json: Annotated[Path, Parameter(help="Path to the main index.json file")],
) -> None:
    """Build index from the JSON file."""
    Index.build(index_json, DEFAULT_INDEX_PATH)


@app.command(name="render")
def render_command(
    layout: Annotated[Path, Parameter(help="Path to the input YAML layout file")],
    output: Annotated[
        Path | None,
        Parameter(
            ["--output", "-o"],
            help="Path to the output PDF file (default: <input_base>.pdf)",
        ),
    ] = None,
    index: Annotated[
        Path,
        Parameter(
            "--index",
            help=f"Path to the index SQLite file (default: {DEFAULT_INDEX_PATH})",
        ),
    ] = DEFAULT_INDEX_PATH,
) -> None:
    """Render a PDF setbook from a YAML layout file."""
    output_path = output if output else layout.with_name(f"{layout.stem}.pdf")
    render(layout, output_path, index)


@app.command(name="lookup")
def lookup_command(
    title: Annotated[
        list[str],
        Parameter(help="One or more titles (or partial titles) to search for"),
    ],
    output: Annotated[
        Path | None,
        Parameter(
            ["--output", "-o"],
            help="Output path: if file, use as-is; if directory, save <title>.pdf there; default: <title>.pdf in cwd",
        ),
    ] = None,
    index: Annotated[
        Path,
        Parameter(
            "--index",
            help=f"Path to the index SQLite file (default: {DEFAULT_INDEX_PATH})",
        ),
    ] = DEFAULT_INDEX_PATH,
) -> None:
    """Look up titles in the index and extract them to PDF."""

    for item in title:
        render_module.lookup_and_extract(item, output, index)


def main(args: Sequence[str] | None = None) -> None:
    app(args, result_action="return_value")


if __name__ == "__main__":
    main()
