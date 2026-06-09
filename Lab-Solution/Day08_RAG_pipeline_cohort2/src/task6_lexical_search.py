"""
Task 6 — Lexical Search Module (BM25).

BM25 hoạt động thế nào:
    - Term Frequency (TF): từ xuất hiện nhiều trong document → điểm cao
    - Inverse Document Frequency (IDF): từ hiếm → quan trọng hơn
    - Document length normalization: document dài không bị ưu tiên quá mức
    - Formula: score(q,d) = Σ IDF(qi) * (tf(qi,d) * (k1+1)) / (tf(qi,d) + k1*(1-b+b*|d|/avgdl))
    - k1=1.5 (term saturation), b=0.75 (length normalization)

Corpus được load lazy từ data/vector_store/chunks.json.
"""

import json
from pathlib import Path

from .task4_chunking_indexing import (
    CHUNKS_FILE, STANDARDIZED_DIR,
    load_documents, chunk_documents,
)

# Cache
_bm25 = None
_corpus: list[dict] = []


def _load_corpus() -> list[dict]:
    """Load corpus từ chunks.json hoặc build từ standardized files."""
    if CHUNKS_FILE.exists():
        return json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))

    # Fallback: build corpus trực tiếp từ standardized files
    if any(STANDARDIZED_DIR.rglob("*.md")):
        docs = load_documents()
        if docs:
            return chunk_documents(docs)
    return []


def build_bm25_index(corpus: list[dict]):
    """
    Xây dựng BM25Okapi index từ corpus.

    Args:
        corpus: List of {'content': str, 'metadata': dict}
    Returns:
        BM25Okapi instance
    """
    from rank_bm25 import BM25Okapi

    # Tokenize đơn giản bằng split() — đủ tốt cho tiếng Việt trong context này
    tokenized_corpus = [doc["content"].lower().split() for doc in corpus]
    return BM25Okapi(tokenized_corpus)


def _get_bm25():
    """Lazy-load BM25 index và corpus."""
    global _bm25, _corpus
    if _bm25 is None:
        _corpus = _load_corpus()
        if _corpus:
            _bm25 = build_bm25_index(_corpus)
    return _bm25, _corpus


def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm từ khóa sử dụng BM25Okapi.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,      # BM25 score
            'metadata': dict
        }
        Sorted by score descending.
    """
    bm25, corpus = _get_bm25()
    if bm25 is None or not corpus:
        return []

    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    k = min(top_k, len(corpus))
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]

    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            results.append({
                "content": corpus[idx]["content"],
                "score": float(scores[idx]),
                "metadata": corpus[idx].get("metadata", {}),
            })

    return results


if __name__ == "__main__":
    results = lexical_search("Điều 248 tàng trữ trái phép chất ma tuý", top_k=5)
    for r in results:
        print(f"[{r['score']:.3f}] {r['content'][:100]}...")
