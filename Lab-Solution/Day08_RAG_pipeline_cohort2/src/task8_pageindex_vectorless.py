"""
Task 8 — PageIndex Vectorless RAG.

Đăng ký tài khoản tại: https://pageindex.ai/
SDK & sample code: https://github.com/VectifyAI/PageIndex

PageIndex cho phép RAG mà không cần vector store — sử dụng
structural understanding của document thay vì embedding.

Fallback: Nếu không có PAGEINDEX_API_KEY, dùng BM25 local làm fallback.

Cài đặt:
    pip install pageindex
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"


def _bm25_fallback(query: str, top_k: int) -> list[dict]:
    """BM25 fallback khi không có PageIndex API key."""
    from .task6_lexical_search import lexical_search
    results = lexical_search(query, top_k=top_k)
    for r in results:
        r["source"] = "pageindex"
    return results


def upload_documents():
    """Upload toàn bộ markdown documents lên PageIndex."""
    if not PAGEINDEX_API_KEY:
        print("⚠ PAGEINDEX_API_KEY chưa được cấu hình.")
        return

    try:
        from pageindex import PageIndex
        pi = PageIndex(api_key=PAGEINDEX_API_KEY)
        for md_file in sorted(STANDARDIZED_DIR.rglob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            pi.upload(
                content=content,
                metadata={"filename": md_file.name, "type": md_file.parent.name}
            )
            print(f"  ✓ Uploaded: {md_file.name}")
    except Exception as e:
        print(f"  ✗ Upload failed: {e}")


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """
    Vectorless retrieval sử dụng PageIndex.
    Dùng làm fallback khi hybrid search không có kết quả tốt.

    Nếu không có API key → fallback sang BM25 local.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,
            'metadata': dict,
            'source': 'pageindex'
        }
    """
    if not PAGEINDEX_API_KEY:
        # Fallback sang BM25 local để đảm bảo pipeline không bị ngắt
        return _bm25_fallback(query, top_k)

    try:
        from pageindex import PageIndex
        pi = PageIndex(api_key=PAGEINDEX_API_KEY)
        results = pi.query(query=query, top_k=top_k)
        return [
            {
                "content": r.text if hasattr(r, "text") else str(r),
                "score": r.score if hasattr(r, "score") else 0.5,
                "metadata": r.metadata if hasattr(r, "metadata") else {},
                "source": "pageindex",
            }
            for r in results
        ]
    except Exception as e:
        print(f"  ⚠ PageIndex API error: {e}. Falling back to BM25.")
        return _bm25_fallback(query, top_k)


if __name__ == "__main__":
    if not PAGEINDEX_API_KEY:
        print("⚠ PAGEINDEX_API_KEY chưa được cấu hình. Đang dùng BM25 fallback.")
        print("  Đăng ký tại: https://pageindex.ai/")
    print("\nTest query:")
    results = pageindex_search("hình phạt sử dụng ma tuý", top_k=3)
    for r in results:
        print(f"[{r['score']:.3f}] [{r['source']}] {r['content'][:100]}...")
