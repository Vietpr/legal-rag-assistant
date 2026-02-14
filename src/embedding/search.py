import sys
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer
import chromadb

# CONFIG
CHROMA_DIR = Path("data/vectordb")
COLLECTION_NAME = "legal_chunks"
MODEL_NAME = "BAAI/bge-m3"

# Search defaults
DEFAULT_TOP_K = 5
FINAL_TOP_K = 3


def init_search():
    """Load model and connect to ChromaDB."""
    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION_NAME)
    return model, collection


def search(
    query: str,
    model: SentenceTransformer,
    collection,
    top_k: int = DEFAULT_TOP_K,
    version: str = None,
    law_type: str = None,
) -> list[dict]:
    """
    Semantic search + metadata filter + re-rank by issued_year.

    Args:
        query: Legal question (Vietnamese)
        model: SentenceTransformer model (pre-loaded)
        collection: ChromaDB collection
        top_k: Number of initial semantic search results
        version: Filter by version (e.g., "update_law")
        law_type: Filter by law type (e.g., "Nghị định")

    Returns:
        List of result dicts, sorted by issued_year DESC
    """
    # 1. Embed query
    query_embedding = model.encode([query], normalize_embeddings=True).tolist()

    # 2. Build metadata filter
    where_filter = None
    conditions = []
    if version:
        conditions.append({"version": version})
    if law_type:
        conditions.append({"law_type": law_type})

    if len(conditions) == 1:
        where_filter = conditions[0]
    elif len(conditions) > 1:
        where_filter = {"$and": conditions}

    # 3. ChromaDB query
    query_params = {
        "query_embeddings": query_embedding,
        "n_results": top_k,
    }
    if where_filter:
        query_params["where"] = where_filter

    results = collection.query(**query_params)

    # 4. Parse results
    parsed = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        parsed.append({
            "chunk_id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else None,
            **meta,
        })

    # 5. Re-rank: prioritize newer laws (higher issued_year)
    parsed.sort(key=lambda x: x.get("issued_year", 0), reverse=True)

    return parsed[:FINAL_TOP_K]


def format_result(result: dict, rank: int) -> str:
    """Format a single result for CLI output."""
    lines = [
        f"{'='*60}",
        f"Result #{rank}",
        f"{'='*60}",
        f"Law: {result.get('law_title', 'N/A')} ({result.get('law_type', 'N/A')})",
        f"Chapter: {result.get('chapter', 'N/A')}",
        f"Article: {result.get('article', 'N/A')}",
        f"Year: {result.get('issued_year', 'N/A')}",
        f"Version: {result.get('version', 'N/A')}",
        f"Distance: {result.get('distance', 'N/A'):.4f}" if result.get('distance') else "",
        f"{'─'*56}",
        f"Content:",
    ]

    # Truncate text if too long
    text = result.get("text", "")
    if len(text) > 500:
        text = text[:500] + "..."
    for line in text.splitlines():
        lines.append(f"     {line}")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python src/embedding/search.py <query> [--version update_law] [--type Luật]")
        print()
        print("Examples:")
        print('  python src/embedding/search.py "mức lương tối thiểu vùng"')
        print('  python src/embedding/search.py "bảo hiểm y tế" --version update_law')
        print('  python src/embedding/search.py "trợ cấp thất nghiệp" --type Luật')
        sys.exit(1)

    query = sys.argv[1]
    version = None
    law_type = None

    # Parse optional args
    args = sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--version" and i + 1 < len(args):
            version = args[i + 1]
        elif arg == "--type" and i + 1 < len(args):
            law_type = args[i + 1]

    print(f"Query: \"{query}\"")
    if version:
        print(f"Filter version: {version}")
    if law_type:
        print(f"Filter law_type: {law_type}")
    print()

    # Init
    print("Loading model & DB...")
    model, collection = init_search()
    print(f"Ready! Collection has {collection.count()} chunks")
    print()

    # Search
    results = search(query, model, collection, version=version, law_type=law_type)

    if not results:
        print("No matching results found.")
        return

    print(f"Top {len(results)} results (prioritizing latest laws):\n")
    for i, result in enumerate(results, 1):
        print(format_result(result, i))
        print()


if __name__ == "__main__":
    main()
