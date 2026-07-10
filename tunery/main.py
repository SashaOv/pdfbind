"""Tunery CLI - Build PDF setbooks from sheet music collections."""

from pathlib import Path
from typing import Annotated, Sequence

from cyclopts import App, Parameter

import tunery.render as render_module
from tunery.render import render

app = App(help="Tunery: Build PDF setbooks from sheet music collections")


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
) -> None:
    """Render a PDF setbook from a YAML layout file."""
    output_path = output if output else layout.with_name(f"{layout.stem}.pdf")
    render(layout, output_path)


@app.command(name="lookup")
def lookup_command(
    title: Annotated[
        list[str],
        Parameter(
            help="One or more tune titles to search for",
            negative_iterable=(),
        ),
    ],
    output: Annotated[
        Path | None,
        Parameter(
            ["--output", "-o"],
            help="Output path: if file, use as-is; if directory, save TITLE.pdf there; default: TITLE.pdf in cwd",
        ),
    ] = None,
) -> None:
    """Look up titles in configured libraries and extract them to PDF."""

    for item in title:
        render_module.lookup_and_extract(item, output)


def main(args: Sequence[str] | None = None) -> None:
    app(args, result_action="return_value")


if __name__ == "__main__":
    main()
