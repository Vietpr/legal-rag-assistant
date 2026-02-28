import os
import re
import time
import datetime
from pathlib import Path
from dotenv import load_dotenv
from google import genai

from sentence_transformers import SentenceTransformer
import chromadb

from src.api.prompts import SYSTEM_PROMPT, build_prompt


# CONFIG
load_dotenv()

CHROMA_DIR = Path("data/vectordb")
COLLECTION_NAME = "legal_chunks"
MODEL_NAME = "BAAI/bge-m3"
GEMINI_MODEL = "gemini-2.5-flash"

# Search params
SEARCH_TOP_K = 7   # Retrieve top-7 from ChromaDB
FINAL_TOP_K = 5    # After re-rank, keep top-5 for context


class LegalRAG:
    def __init__(self):
        self.embedding_model = None
        self.collection = None
        self.gemini_client = None

    def init(self):
        # 1. Embedding model
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer(MODEL_NAME)
        print(f"Embedding model loaded (dim={self.embedding_model.get_sentence_embedding_dimension()})")

        # 2. ChromaDB
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = client.get_collection(COLLECTION_NAME)
        print(f"ChromaDB connected ({self.collection.count()} chunks)")

        # 3. Gemini client
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found! Set it in .env file.")
        self.gemini_client = genai.Client(api_key=api_key)
        print("Gemini client ready")

    def search(
        self,
        query: str,
        top_k: int = SEARCH_TOP_K,
        version: str = None,
        law_type: str = None,
    ) -> list[dict]:
        # Embed query
        query_embedding = self.embedding_model.encode(
            [query], normalize_embeddings=True
        ).tolist()

        # Build filter
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

        # Query ChromaDB
        query_params = {
            "query_embeddings": query_embedding,
            "n_results": top_k,
        }
        if where_filter:
            query_params["where"] = where_filter

        results = self.collection.query(**query_params)

        # Parse
        parsed = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            parsed.append({
                "chunk_id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
                **meta,
            })

        # Re-rank: combine semantic relevance (distance) with year recency
        # Lower distance = more relevant. We want relevance-first ranking.
        current_year = datetime.datetime.now().year

        for p in parsed:
            distance = p.get("distance", 1.0)
            year = p.get("issued_year") or 2000
            # Normalize year bonus: max 0.05 bonus for current year, 0 for very old
            year_bonus = max(0, (year - 2000) / (current_year - 2000)) * 0.05
            # Combined score: lower is better (distance - year_bonus)
            p["score"] = distance - year_bonus

        parsed.sort(key=lambda x: x.get("score", 1.0))

        # Deduplicate: keep only 1 chunk per article (the most relevant one)
        seen_articles = set()
        deduped = []
        for p in parsed:
            article_key = f"{p.get('law_name', '')}_{p.get('article', '')}"
            if article_key not in seen_articles:
                seen_articles.add(article_key)
                deduped.append(p)

        return deduped[:FINAL_TOP_K]

    def expand_chunks(self, chunks: list[dict]) -> list[dict]:
        """Expand multi-part chunks: if a chunk is part of a split article
        (chunk_id ends with _p1, _p2, ...), fetch all sibling parts
        and merge their texts so the full article is in context."""
        expanded = []

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id", "")
            match = re.match(r"(.+)_p(\d+)$", chunk_id)

            if not match:
                # Single chunk article, no expansion needed
                expanded.append(chunk)
                continue

            base_id = match.group(1)

            # Try fetching parts p1 through p10 (covers all cases)
            part_ids = [f"{base_id}_p{i}" for i in range(1, 11)]
            try:
                result = self.collection.get(ids=part_ids)
                if result and result["ids"]:
                    # Sort parts by part number
                    parts = []
                    for i, pid in enumerate(result["ids"]):
                        part_num = int(re.search(r"_p(\d+)$", pid).group(1))
                        parts.append({
                            "part_num": part_num,
                            "text": result["documents"][i],
                        })
                    parts.sort(key=lambda x: x["part_num"])

                    # Merge all part texts into the chunk
                    merged_text = "\n".join(p["text"] for p in parts)
                    merged_chunk = dict(chunk)
                    merged_chunk["text"] = merged_text
                    merged_chunk["expanded_parts"] = len(parts)
                    expanded.append(merged_chunk)
                    print(f"Expanded {base_id}: merged {len(parts)} parts")
                else:
                    expanded.append(chunk)
            except Exception as e:
                print(f"Chunk expansion failed for {chunk_id}: {e}")
                expanded.append(chunk)

        return expanded

    def ask(
        self,
        question: str,
        version: str = None,
        law_type: str = None,
    ) -> dict:
        """Full RAG: search → build prompt → call Gemini → return answer + citations."""

        # 1. Search
        chunks = self.search(question, version=version, law_type=law_type)

        # 1.5 Expand multi-part chunks (fetch all parts of split articles)
        chunks = self.expand_chunks(chunks)

        if not chunks:
            return {
                "answer": "Không tìm thấy điều luật liên quan trong cơ sở dữ liệu.",
                "citations": [],
                "chunks_used": 0,
            }

        # 2. Build prompt
        user_prompt = build_prompt(question, chunks)

        # 3. Call Gemini (with retry for rate limits)
        answer = None
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = self.gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=user_prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.1,
                        max_output_tokens=8192,
                    ),
                )
                answer = response.text
                break
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait = (attempt + 1) * 15  # 15s, 30s, 45s
                    print(f"Rate limited, retrying in {wait}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait)
                else:
                    answer = f"Gemini API error: {error_msg}"
                    break

        if answer is None:
            answer = "Gemini API is rate limited. Please try again after 1 minute."

        # 4. Build citations
        citations = []
        for chunk in chunks:
            citations.append({
                "article": chunk.get("article", ""),
                "law_title": chunk.get("law_title", ""),
                "law_type": chunk.get("law_type", ""),
                "chapter": chunk.get("chapter", ""),
                "issued_year": chunk.get("issued_year"),
                "version": chunk.get("version", ""),
                "source_file": chunk.get("source_file", ""),
                "distance": chunk.get("distance"),
            })

        return {
            "answer": answer,
            "citations": citations,
            "chunks_used": len(chunks),
        }


# Singleton instance
rag = LegalRAG()
