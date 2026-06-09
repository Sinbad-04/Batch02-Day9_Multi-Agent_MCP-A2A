"""
Task 5 — Semantic Search Module.

Dense retrieval sử dụng TF-IDF cosine similarity trên vector store từ Task 4.
Tự động build vector store từ data/standardized/ nếu chưa có index.

Note: Sử dụng TF-IDF thay vì sentence-transformers để hoạt động offline.
Có thể nâng cấp lên semantic search thực sự bằng cách thay vectorizer
bằng SentenceTransformer khi có internet ổn định.
"""

import json
import pickle
import numpy as np
from pathlib import Path

from .task4_chunking_indexing import (
    CHUNKS_FILE, EMBEDDINGS_FILE, VECTORIZER_FILE, STANDARDIZED_DIR,
    load_documents, chunk_documents, embed_chunks, index_to_vectorstore,
)

# Cache trong memory
_chunks: list[dict] | None = None
_embeddings: np.ndarray | None = None
_vectorizer = None


def _load_vectorizer():
    global _vectorizer
    if _vectorizer is None and VECTORIZER_FILE.exists():
        with open(VECTORIZER_FILE, "rb") as f:
            _vectorizer = pickle.load(f)
    return _vectorizer


def _load_index():
    """Load index từ disk. Nếu chưa có, tự build từ standardized files."""
    global _chunks, _embeddings

    if _chunks is not None and _embeddings is not None:
        return _chunks, _embeddings

    if not CHUNKS_FILE.exists() or not EMBEDDINGS_FILE.exists():
        _build_index_from_standardized()

    if not CHUNKS_FILE.exists():
        _chunks, _embeddings = [], np.array([], dtype=np.float32)
        return _chunks, _embeddings

    _chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
    _embeddings = np.load(str(EMBEDDINGS_FILE))
    _load_vectorizer()
    return _chunks, _embeddings


def _build_index_from_standardized():
    """Build index tự động từ standardized files nếu chưa có."""
    if not any(STANDARDIZED_DIR.rglob("*.md")):
        return
    print("[Task 5] Building TF-IDF index from standardized files...")
    docs = load_documents()
    if not docs:
        return
    chunks = chunk_documents(docs)
    chunks = embed_chunks(chunks)
    index_to_vectorstore(chunks)
    _load_vectorizer()


def _cosine_similarity(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Tính cosine similarity giữa query vector và embedding matrix."""
    q_norm = np.linalg.norm(query_vec)
    if q_norm < 1e-10:
        return np.zeros(len(matrix))
    query_unit = query_vec / q_norm
    row_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    row_norms = np.where(row_norms < 1e-10, 1.0, row_norms)
    matrix_unit = matrix / row_norms
    return matrix_unit @ query_unit


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm ngữ nghĩa sử dụng TF-IDF cosine similarity.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,      # Cosine similarity [0, 1]
            'metadata': dict
        }
        Sorted by score descending.
    """
    chunks, embeddings = _load_index()
    if not chunks or len(embeddings) == 0:
        return []

    vectorizer = _load_vectorizer()
    if vectorizer is None:
        return []

    # Embed query với cùng TF-IDF vectorizer
    query_vec = vectorizer.transform([query]).toarray()[0].astype(np.float32)
    scores = _cosine_similarity(query_vec, embeddings)

    k = min(top_k, len(chunks))
    top_indices = np.argsort(scores)[::-1][:k]

    results = []
    for idx in top_indices:
        results.append({
            "content": chunks[idx]["content"],
            "score": float(scores[idx]),
            "metadata": chunks[idx].get("metadata", {}),
        })

    return results


if __name__ == "__main__":
    results = semantic_search("hình phạt cho tội tàng trữ ma tuý", top_k=5)
    for r in results:
        print(f"[{r['score']:.3f}] {r['content'][:100]}...")
