import re
from pathlib import Path
from tqdm import tqdm

INPUT_DIR = Path("data/extracted_text")
OUTPUT_DIR = Path("data/clean_text")

# 1. HEADER PATTERNS — Remove header section of legal documents
HEADER_PATTERNS = [
    # Issuing authority name
    r"^CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\s*$",
    r"^Độc lập\s*[-–]\s*Tự do\s*[-–]\s*Hạnh phúc\s*$",
    r"^VĂN PHÒNG QUỐC HỘI\s*$",
    r"^QUỐC HỘI\s*$",
    r"^CHÍNH PHỦ\s*$",
    r"^BỘ\s+.+$",
    # Document number, issue date
    r"^Số:\s.*",
    r"^Luật số:\s.*",
    r"^Hà Nội, ngày\s.*",
    # Separator lines
    r"^-{3,}$",
    # Document type (title block)
    r"^LUẬT\s*$",
    r"^NGHỊ ĐỊNH\s*$",
    r"^THÔNG TƯ\s*$",
    # Legal basis (preamble)
    r"^Căn cứ Hiến pháp\b.*",
    r"^Căn cứ Luật\b.*",
    r"^Căn cứ Bộ luật\b.*",
    r"^Theo đề nghị của\b.*",
    # Issuance lines
    r"^Quốc hội ban hành\b.*",
    r"^Chính phủ ban hành\b.*",
]

# 2. FOOTER PATTERNS — Detect the start of footer section
FOOTER_START_PATTERNS = [
    r"^Nơi nhận:\s*$",
    r"^TM\.\s*CHÍNH PHỦ",
    r"^CHỦ TỊCH QUỐC HỘI",
    r"^CHỦ TỊCH\s*$",
    r"^KT\.\s*THỦ TƯỚNG",
    r"^PHÓ THỦ TƯỚNG",
    r"^BỘ TRƯỞNG\s*$",
    # VBHN (consolidated document) specific
    r"^XÁC THỰC VĂN BẢN HỢP NHẤT",
    r"^CHỦ NHIỆM\s*$",
]

# 3. LEGAL STRUCTURE MARKERS — Lines that need a blank line before them
STRUCTURE_MARKERS = [
    r"^Chương\s+",       # Chương I, Chương II, ...
    r"^CHƯƠNG\s+",       # CHƯƠNG I, ...
    r"^Điều\s+\d+",      # Điều 1, Điều 2, ...
    r"^MỤC\s+\d+",       # MỤC 1, MỤC 2, ...
    r"^Mục\s+\d+",       # Mục 1, ...
    r"^PHẦN\s+",         # PHẦN I, ...
]

# Pattern to detect split chapter title lines (UPPERCASE line right after "Chương X")
CHAPTER_LINE_RE = re.compile(r"^(Chương|CHƯƠNG)\s+[\dIVXLCDM]+\.?\s*$")
UPPERCASE_TITLE_RE = re.compile(r"^[A-ZÀ-Ỹ\s,\-–]+$")


def is_header_line(line: str) -> bool:
    """Check if a line is a header line that should be removed."""
    for pattern in HEADER_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False


def is_footer_start(line: str) -> bool:
    """Check if a line marks the start of the footer section."""
    for pattern in FOOTER_START_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def is_structure_marker(line: str) -> bool:
    """Check if a line is a legal structure marker."""
    for pattern in STRUCTURE_MARKERS:
        if re.search(pattern, line):
            return True
    return False


def remove_footnote_markers(line: str) -> str:
    """Remove footnote markers [1], [2], [29], ... from content."""
    return re.sub(r"\[\d+\]", "", line)


def clean_text(text: str) -> str:
    """
    Clean legal document text:
    - Remove header/footer/separator/footnote markers
    - Preserve Chapter–Article–Clause–Point structure
    - Insert blank lines before structure markers
    - Merge split chapter title lines
    """
    lines = text.splitlines()
    cleaned_lines = []
    footer_reached = False

    for i, line in enumerate(lines):
        line = line.strip()

        # If footer is reached, skip everything from here on
        if is_footer_start(line):
            footer_reached = True
        if footer_reached:
            continue

        # Skip blank lines (handled later)
        if not line:
            continue

        # Skip header lines
        if is_header_line(line):
            continue

        # Remove footnote markers [1], [2], ...
        line = remove_footnote_markers(line)

        # Remove excess whitespace after footnote removal
        line = re.sub(r"\s{2,}", " ", line).strip()

        if not line:
            continue

        cleaned_lines.append(line)

    # === POST-PROCESSING ===

    # Phase 1: Merge split chapter title lines
    # "Chương I" + "NHỮNG QUY ĐỊNH CHUNG" → "Chương I. NHỮNG QUY ĐỊNH CHUNG"
    merged_lines = []
    skip_next = False

    for i, line in enumerate(cleaned_lines):
        if skip_next:
            skip_next = False
            continue

        if CHAPTER_LINE_RE.match(line) and i + 1 < len(cleaned_lines):
            next_line = cleaned_lines[i + 1]
            if UPPERCASE_TITLE_RE.match(next_line):
                separator = ". " if not line.rstrip().endswith(".") else " "
                merged_lines.append(line.rstrip(".") + separator + next_line)
                skip_next = True
                continue

        merged_lines.append(line)

    # Phase 2: Insert blank lines before legal structure markers
    final_lines = []
    for i, line in enumerate(merged_lines):
        if is_structure_marker(line) and i > 0:
            # Only add blank line if previous line is not already blank
            if final_lines and final_lines[-1] != "":
                final_lines.append("")
        final_lines.append(line)

    # Phase 3: Collapse multiple consecutive blank lines into one
    result_lines = []
    for line in final_lines:
        if line == "" and result_lines and result_lines[-1] == "":
            continue
        result_lines.append(line)

    return "\n".join(result_lines)


def process_folder(input_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    for txt_file in tqdm(list(input_dir.glob("*.txt")), desc=input_dir.name):
        raw_text = txt_file.read_text(encoding="utf-8")
        cleaned_text = clean_text(raw_text)

        out_file = output_dir / txt_file.name
        out_file.write_text(cleaned_text, encoding="utf-8")


def main():
    for subfolder in ["origin_law", "update_law"]:
        input_dir = INPUT_DIR / subfolder
        output_dir = OUTPUT_DIR / subfolder

        if input_dir.exists():
            process_folder(input_dir, output_dir)
        else:
            print(f"Skip {subfolder}, folder not found")


if __name__ == "__main__":
    main()
