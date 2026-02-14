import re
import json
from pathlib import Path
from tqdm import tqdm


INPUT_DIR = Path("data/clean_text")
OUTPUT_FILE = Path("data/chunks/legal_chunks.jsonl")

# Max character threshold per chunk (~512 Vietnamese tokens)
MAX_CHUNK_CHARS = 2000


# REGEX PATTERNS
# Real article header: "Điều 49. Điều kiện hưởng" (number + period + title)
# NOT mid-text ref: "Điều 49 của Luật này." or "Điều 112, Điều 113..."
ARTICLE_PATTERN = re.compile(r"^Điều\s+\d+\w*\.\s+\S")
CHAPTER_PATTERN = re.compile(r"^(Chương\s+[\dIVXLCDM]+\.?\s*.*)$", re.IGNORECASE)
SECTION_PATTERN = re.compile(r"^(MỤC\s+\d+\.?\s*.*)$", re.IGNORECASE)
CLAUSE_PATTERN = re.compile(r"^(\d+)\.\s")  # Clause: 1. 2. 3. ...


def extract_metadata_from_filename(filename: str):
    parts = filename.split("_")
    year = None
    law_type = "Unknown"

    for p in parts:
        if p.isdigit() and len(p) == 4:
            year = int(p)

    if "ND-CP" in filename:
        law_type = "Nghị định"
    elif "TT-" in filename:
        law_type = "Thông tư"
    elif "VBHN" in filename:
        law_type = "Văn bản hợp nhất"
    elif "QH" in filename:
        law_type = "Luật"

    return year, law_type


def extract_article_number(article_header: str) -> str:
    """Extract article number from header. E.g.: 'Điều 12. Đối tượng...' → '12'"""
    match = re.search(r"Điều\s+(\d+\w*)", article_header)
    return match.group(1) if match else "0"


def split_long_article(article_header: str, content: str, max_chars: int = MAX_CHUNK_CHARS):
    if len(content) <= max_chars:
        return [(article_header, content)]

    lines = content.splitlines()
    sub_chunks = []
    current_lines = []
    current_len = 0

    # First line is always the article header
    header_line = lines[0] if lines else article_header
    header_len = len(header_line) + 1

    for line in lines[1:]:
        line_len = len(line) + 1  # +1 for newline

        # If a new clause is found and buffer is long enough → split
        is_clause_start = CLAUSE_PATTERN.match(line.strip())
        would_exceed = (current_len + header_len + line_len) > max_chars

        if is_clause_start and current_lines and would_exceed:
            chunk_text = header_line + "\n" + "\n".join(current_lines)
            sub_chunks.append((article_header, chunk_text))
            current_lines = []
            current_len = 0

        current_lines.append(line)
        current_len += line_len

    # Remaining content
    if current_lines:
        chunk_text = header_line + "\n" + "\n".join(current_lines)
        sub_chunks.append((article_header, chunk_text))

    if not sub_chunks:
        sub_chunks = [(article_header, content)]

    final_chunks = []
    for header, chunk_text in sub_chunks:
        if len(chunk_text) <= max_chars:
            final_chunks.append((header, chunk_text))
        else:
            # Force-split at line boundaries
            c_lines = chunk_text.splitlines()
            c_header = c_lines[0]
            c_buf = []
            c_len = 0
            for cl in c_lines[1:]:
                cl_len = len(cl) + 1
                if (c_len + len(c_header) + 1 + cl_len) > max_chars and c_buf:
                    final_chunks.append((header, c_header + "\n" + "\n".join(c_buf)))
                    c_buf = []
                    c_len = 0
                c_buf.append(cl)
                c_len += cl_len
            if c_buf:
                final_chunks.append((header, c_header + "\n" + "\n".join(c_buf)))

    return final_chunks if final_chunks else [(article_header, content)]


def chunk_by_article(text: str):
    """
    Chunk text by article, tracking chapter and section context.
    Returns list of dicts with full context.
    """
    chunks = []
    current_chapter = None
    current_section = None
    current_article = None
    buffer = []
    law_title = None

    for line in text.splitlines():
        stripped = line.strip()

        # Track chapter
        if CHAPTER_PATTERN.match(stripped):
            # Flush buffer before changing chapter
            if current_article and buffer:
                chunks.append({
                    "article_header": current_article,
                    "content": "\n".join(buffer),
                    "chapter": current_chapter,
                    "section": current_section,
                })
                buffer = []
                current_article = None

            current_chapter = stripped
            current_section = None  # Reset section when entering new chapter
            continue

        # Track section
        if SECTION_PATTERN.match(stripped):
            # Flush buffer before changing section
            if current_article and buffer:
                chunks.append({
                    "article_header": current_article,
                    "content": "\n".join(buffer),
                    "chapter": current_chapter,
                    "section": current_section,
                })
                buffer = []
                current_article = None

            current_section = stripped
            continue

        # New article found
        if ARTICLE_PATTERN.match(stripped):
            # Flush previous article
            if current_article and buffer:
                chunks.append({
                    "article_header": current_article,
                    "content": "\n".join(buffer),
                    "chapter": current_chapter,
                    "section": current_section,
                })
                buffer = []

            current_article = stripped
            buffer.append(stripped)
            continue

        # Text before first article → save as law_title
        if current_article is None and stripped:
            if law_title is None:
                law_title = stripped
            continue

        # Content belonging to current article
        if current_article:
            buffer.append(line)

    # Flush last article
    if current_article and buffer:
        chunks.append({
            "article_header": current_article,
            "content": "\n".join(buffer),
            "chapter": current_chapter,
            "section": current_section,
        })

    return chunks, law_title


def process_file(txt_path: Path, version: str):
    """Process a single text file → list of chunk dicts."""
    text = txt_path.read_text(encoding="utf-8")
    year, law_type = extract_metadata_from_filename(txt_path.name)

    raw_chunks, law_title = chunk_by_article(text)
    results = []

    for chunk_data in raw_chunks:
        article_header = chunk_data["article_header"]
        content = chunk_data["content"]
        article_num = extract_article_number(article_header)

        # Split overly long articles at clause boundaries
        sub_chunks = split_long_article(article_header, content)

        for idx, (header, sub_content) in enumerate(sub_chunks):
            # Create chunk_id — always add _part_ when there are multiple sub-chunks
            chunk_id = f"{txt_path.stem}_dieu_{article_num}"
            if len(sub_chunks) > 1:
                chunk_id += f"_p{idx + 1}"

            text_clean = sub_content.strip()

            results.append({
                "chunk_id": chunk_id,
                "text": text_clean,
                "law_name": txt_path.stem,
                "law_title": law_title,
                "law_type": law_type,
                "chapter": chunk_data["chapter"],
                "section": chunk_data["section"],
                "article": article_header,
                "issued_year": year,
                "source_file": txt_path.name,
                "version": version,
                "char_count": len(text_clean),
            })

    return results


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    total_chunks = 0

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for version in ["origin_law", "update_law"]:
            dir_path = INPUT_DIR / version
            if not dir_path.exists():
                continue

            for txt_file in tqdm(list(dir_path.glob("*.txt")), desc=version):
                chunks = process_file(txt_file, version)
                for chunk in chunks:
                    f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    total_chunks += 1

    print(f"Done! Total chunks: {total_chunks}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
