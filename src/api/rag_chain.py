import os
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
GEMINI_MODEL = "gemini-2.0-flash"

# Search params
SEARCH_TOP_K = 5   # Retrieve top-5 from ChromaDB
FINAL_TOP_K = 3    # After re-rank, keep top-3 for context


class LegalRAG:
    """Legal RAG pipeline: Search + Gemini."""

    def __init__(self):
        self._embedding_model = None
        self._collection = None
        self._gemini_client = None

    def init(self):
        # 1. Embedding model
        print("Loading embedding model...")
        self._embedding_model = SentenceTransformer(MODEL_NAME)
        print(f"Embedding model loaded (dim={self._embedding_model.get_sentence_embedding_dimension()})")

        # 2. ChromaDB
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._collection = client.get_collection(COLLECTION_NAME)
        print(f"ChromaDB connected ({self._collection.count()} chunks)")

        # 3. Gemini client
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found! Set it in .env file.")
        self._gemini_client = genai.Client(api_key=api_key)
        print("Gemini client ready")

    def search(
        self,
        query: str,
        top_k: int = SEARCH_TOP_K,
        version: str = None,
        law_type: str = None,
    ) -> list[dict]:
        # Embed query
        query_embedding = self._embedding_model.encode(
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

        results = self._collection.query(**query_params)

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

        # Re-rank by issued_year DESC
        parsed.sort(key=lambda x: x.get("issued_year", 0), reverse=True)

        return parsed[:FINAL_TOP_K]

    def ask(
        self,
        question: str,
        version: str = None,
        law_type: str = None,
    ) -> dict:
        """Full RAG: search → build prompt → call Gemini → return answer + citations."""

        # 1. Search
        chunks = self.search(question, version=version, law_type=law_type)

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
                response = self._gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=user_prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.1,
                        max_output_tokens=2048,
                    ),
                )
                answer = response.text
                break
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait = (attempt + 1) * 15  # 15s, 30s, 45s
                    print(f"Rate limited, retrying in {wait}s... (attempt {attempt + 1}/{max_retries})")
                    import time
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
