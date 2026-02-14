import fitz  # pymupdf
from pathlib import Path
from tqdm import tqdm

RAW_PDF_DIR = Path("data/raw_pdf")
OUTPUT_DIR = Path("data/extracted_text")


def extract_text_from_pdf(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    texts = []

    for page in doc:
        text = page.get_text("text")
        if text.strip():
            texts.append(text)

    return "\n".join(texts)


def process_folder(input_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = list(input_dir.glob("*.pdf"))

    for pdf_file in tqdm(pdf_files, desc=f"Processing {input_dir.name}"):
        text = extract_text_from_pdf(pdf_file)

        output_file = output_dir / f"{pdf_file.stem}.txt"
        output_file.write_text(text, encoding="utf-8")


def main():
    for subfolder in ["origin_law", "update_law"]:
        input_dir = RAW_PDF_DIR / subfolder
        output_dir = OUTPUT_DIR / subfolder

        if not input_dir.exists():
            print(f"Skip {subfolder}, folder not found")
            continue

        process_folder(input_dir, output_dir)


if __name__ == "__main__":
    main()
