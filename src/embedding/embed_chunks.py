import json
import sys
from pathlib import Path
from tqdm import tqdm

from sentence_transformers import SentenceTransformer
import chromadb

# CONFIG
INPUT_FILE = Path("data/chunks/legal_chunks.jsonl")
CHROMA_DIR = Path("data/vectordb")
COLLECTION_NAME = "legal_chunks"
MODEL_NAME = "BAAI/bge-m3"
BATCH_SIZE = 64


def load_chunks(filepath: Path) -> list[dict]:
    """Read legal_chunks.jsonl → list of dicts."""
    chunks = []
    with filepath.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    print(f"Loaded {len(chunks)} chunks from {filepath}")
    return chunks


def embed_and_store(chunks: list[dict]):
    """Embed chunks using bge-m3 and store into ChromaDB."""

    # 1. Load model
    print(f"Loading model: {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)
    print(f"Model loaded! Embedding dim: {model.get_sentence_embedding_dimension()}")

    # 2. Init ChromaDB persistent client
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Delete old collection if exists (re-embed from scratch)
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted old collection: {COLLECTION_NAME}")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}  # Cosine similarity
    )

    # 3. Batch embed + upsert
    total = len(chunks)
    for i in tqdm(range(0, total, BATCH_SIZE), desc="Embedding"):
        batch = chunks[i : i + BATCH_SIZE]

        texts = [c["text"] for c in batch]
        ids = [c["chunk_id"] for c in batch]

        # Embed
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

        # Metadata for ChromaDB (only supports str, int, float, bool)
        metadatas = []
        for c in batch:
            metadatas.append({
                "law_name": c.get("law_name", ""),
                "law_title": c.get("law_title") or "",
                "law_type": c.get("law_type", ""),
                "chapter": c.get("chapter") or "",
                "section": c.get("section") or "",
                "article": c.get("article", ""),
                "issued_year": c.get("issued_year") or 0,
                "source_file": c.get("source_file", ""),
                "version": c.get("version", ""),
                "char_count": c.get("char_count", 0),
            })

        # Upsert into ChromaDB
        collection.upsert(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas,
        )

    print(f"Done! Embedded {total} chunks into ChromaDB")
    print(f"DB path: {CHROMA_DIR}")
    print(f"Collection: {COLLECTION_NAME} ({collection.count()} items)")


def main():
    if not INPUT_FILE.exists():
        print(f"File not found: {INPUT_FILE}")
        print("Run chunk_law.py first!")
        sys.exit(1)

    chunks = load_chunks(INPUT_FILE)
    embed_and_store(chunks)


if __name__ == "__main__":
    main()
