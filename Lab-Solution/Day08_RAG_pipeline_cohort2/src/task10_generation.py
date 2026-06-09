"""
Task 10 — Generation Có Citation.

Pipeline:
    1. Retrieve chunks (Task 9)
    2. Reorder để tránh "lost in the middle" (Liu et al. 2023)
    3. Format context với source labels
    4. Inject vào prompt với citation instructions
    5. Gọi LLM và trả về answer có citation

LLM: OpenAI GPT (hoặc Claude nếu có anthropic SDK).
top_k=5: Đủ evidence mà không gây lost in the middle.
top_p=0.9: Diverse nhưng không quá random.
temperature=0.3: Factual output, ít sáng tạo (RAG cần độ chính xác cao).
"""

import os
from dotenv import load_dotenv

load_dotenv()

from .task9_retrieval_pipeline import retrieve


# =============================================================================
# CONFIGURATION
# =============================================================================

TOP_K = 5
TOP_P = 0.9
TEMPERATURE = 0.3

SYSTEM_PROMPT = """Trả lời câu hỏi sau một cách toàn diện bằng tiếng Việt.
Với mỗi khẳng định sự kiện hoặc thông tin, hãy ngay lập tức chèn trích dẫn trong dấu ngoặc
liên kết đến nguồn cụ thể (ví dụ: [Luật Phòng chống ma tuý 2021, Điều 3]
hoặc [VnExpress, 2024]).

Nếu thông tin không được nêu rõ ràng trong ngữ cảnh hoặc cơ sở tri thức được cung cấp,
hãy trả lời 'Tôi không thể xác minh thông tin này từ nguồn hiện có' thay vì đoán.

Quy tắc:
- Chỉ sử dụng thông tin từ ngữ cảnh được cung cấp
- Mỗi khẳng định sự kiện PHẢI có trích dẫn
- Nếu ngữ cảnh không đủ, hãy nói rõ ràng
- Cấu trúc câu trả lời với đoạn văn rõ ràng"""


# =============================================================================
# DOCUMENT REORDERING (tránh lost in the middle)
# =============================================================================

def reorder_for_llm(chunks: list[dict]) -> list[dict]:
    """
    Sắp xếp chunks để tránh "lost in the middle" effect (Liu et al. 2023).

    LLM nhớ tốt thông tin ở ĐẦU và CUỐI prompt, quên thông tin ở GIỮA.
    Strategy: đặt chunks quan trọng nhất ở đầu và cuối, kém quan trọng ở giữa.

    Input:  [0(best), 1, 2, 3, 4]
    Output: [0, 2, 4, 3, 1]
    (indices chẵn trước → quan trọng nhất ở đầu và giữa-cuối,
     indices lẻ đảo ngược → ít quan trọng ở giữa)

    Args:
        chunks: List sorted by score descending (from retrieval)
    Returns:
        List reordered để maximize LLM attention.
    """
    if len(chunks) <= 2:
        return chunks

    # Indices chẵn (0, 2, 4...) → đầu danh sách
    even = [chunks[i] for i in range(0, len(chunks), 2)]
    # Indices lẻ (1, 3, 5...) đảo ngược → cuối danh sách
    odd_reversed = [chunks[i] for i in reversed(range(1, len(chunks), 2))]

    return even + odd_reversed


# =============================================================================
# CONTEXT FORMATTING
# =============================================================================

def format_context(chunks: list[dict]) -> str:
    """
    Format chunks thành context string cho prompt.
    Mỗi chunk có label source để LLM có thể cite.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = meta.get("source", f"source_{i}")
        doc_type = meta.get("type", "unknown")
        context_parts.append(
            f"[Document {i} | Source: {source} | Type: {doc_type}]\n"
            f"{chunk['content']}\n"
        )
    return "\n---\n".join(context_parts)


# =============================================================================
# GENERATION
# =============================================================================

def generate_with_citation(query: str, top_k: int = TOP_K) -> dict:
    """
    End-to-end RAG generation có citation.

    Args:
        query: Câu hỏi của user
        top_k: Số chunks đưa vào context

    Returns:
        {
            'answer': str,           # Câu trả lời có citation
            'sources': list[dict],   # Các chunks đã dùng
            'retrieval_source': str  # 'hybrid' hoặc 'pageindex'
        }
    """
    # Step 1: Retrieve
    chunks = retrieve(query, top_k=top_k)

    if not chunks:
        return {
            "answer": "Tôi không thể xác minh thông tin này từ nguồn hiện có.",
            "sources": [],
            "retrieval_source": "none",
        }

    # Step 2: Reorder để tránh lost in the middle
    reordered = reorder_for_llm(chunks)

    # Step 3: Format context
    context = format_context(reordered)

    # Step 4: Build prompt
    user_message = f"Context:\n{context}\n\n---\n\nCâu hỏi: {query}"

    retrieval_source = chunks[0].get("source", "hybrid")

    # Step 5: Gọi LLM
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        # Trả về answer tổng hợp từ context nếu không có API key
        answer = _synthesize_without_llm(query, reordered)
        return {
            "answer": answer,
            "sources": chunks,
            "retrieval_source": retrieval_source,
        }

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=TEMPERATURE,
        top_p=TOP_P,
        max_tokens=1024,
    )

    answer = response.choices[0].message.content

    return {
        "answer": answer,
        "sources": chunks,
        "retrieval_source": retrieval_source,
    }


def _synthesize_without_llm(query: str, chunks: list[dict]) -> str:
    """
    Tổng hợp câu trả lời từ context mà không cần LLM.
    Dùng khi không có API key — trả về top chunk có citation.
    """
    if not chunks:
        return "Tôi không thể xác minh thông tin này từ nguồn hiện có."

    lines = [f"Dựa trên các nguồn tài liệu về '{query}':\n"]
    for i, chunk in enumerate(chunks[:3], 1):
        meta = chunk.get("metadata", {})
        source = meta.get("source", f"Document {i}")
        lines.append(f"{chunk['content'][:300]}... [{source}]")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    test_queries = [
        "Hình phạt cho tội tàng trữ trái phép chất ma tuý theo pháp luật Việt Nam?",
        "Những nghệ sĩ nào đã bị bắt vì liên quan tới ma tuý?",
    ]

    for q in test_queries:
        print(f"\n{'='*70}")
        print(f"Q: {q}")
        print("=" * 70)
        result = generate_with_citation(q)
        print(f"\nA: {result['answer']}")
        print(f"\n[Sources: {len(result['sources'])} chunks | via {result['retrieval_source']}]")
