import argparse
from pathlib import Path
from typing import Sequence
import yaml
import pikepdf


def parse_args(args: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine PDFs based on YAML input")
    parser.add_argument("layout", help="Path to the input YAML file")
    parser.add_argument("-o", "--output", default=None, help="Path to the output PDF file (default: <input_base>.pdf)")
    return parser.parse_args(args)

def bind_pdf(layout: Path, output: Path):
    with open(str(layout), 'r') as file:
        records = yaml.safe_load(file)

    # Create a new PDF
    combined_pdf = pikepdf.Pdf.new()

    # Create an outline
    outline = []

    # Process each record
    for record in records:
        input_pdf_path = record['file']
        section_name = record.get('title', Path(input_pdf_path).stem)

        # Open the input PDF
        input_pdf = pikepdf.Pdf.open(input_pdf_path)

        # Add pages to the combined PDF
        combined_pdf.pages.extend(input_pdf.pages)

        # Add an outline item
        outline.append(pikepdf.OutlineItem(section_name, len(combined_pdf.pages) - len(input_pdf.pages)))
    
    # Add the outline to the combined PDF
    with combined_pdf.open_outline() as pdf_outline:
        pdf_outline.root.extend(outline)

    # Save the combined PDF
    combined_pdf.save(str(output))
    combined_pdf.close()



def main(args: Sequence[str] | None = None):
    args = parse_args(args)
    input_path = Path(args.layout)
    output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}.pdf")  
    bind_pdf(input_path, output_path)


if __name__ == "__main__":
    main()
