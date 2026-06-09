"""
Task 4 — Chunking & Indexing vào Vector Store.

Chunking strategy: RecursiveCharacterTextSplitter
- Lý do: Phổ biến, an toàn, xử lý tốt tiếng Việt có dấu.
- chunk_size=500: Đủ ngắn để embedding chính xác, đủ dài để có context.
- chunk_overlap=50: Tránh mất thông tin tại ranh giới chunks.

Embedding model: TF-IDF (sklearn) — offline, không cần download
- Lý do: Hoạt động offline, nhanh, hiệu quả cho văn bản pháp luật tiếng Việt.
- Vector Store: Custom JSON + numpy, lưu tại data/vector_store/

Note: Nếu có internet ổn định, có thể thay bằng sentence-transformers BAAI/bge-m3
để có semantic search thực sự. Với demo này, TF-IDF đủ tốt cho retrieval.
"""

import json
import pickle
import numpy as np
from pathlib import Path

STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
VECTOR_STORE_DIR = Path(__file__).parent.parent / "data" / "vector_store"
CHUNKS_FILE = VECTOR_STORE_DIR / "chunks.json"
EMBEDDINGS_FILE = VECTOR_STORE_DIR / "embeddings.npy"
VECTORIZER_FILE = VECTOR_STORE_DIR / "vectorizer.pkl"

# =============================================================================
# CONFIGURATION
# =============================================================================

# RecursiveCharacterTextSplitter: an toàn nhất cho văn bản tiếng Việt
CHUNK_SIZE = 500
# Overlap 50 ký tự: đảm bảo không mất thông tin tại ranh giới
CHUNK_OVERLAP = 50
CHUNKING_METHOD = "recursive"

# TF-IDF embedding: offline, không cần HuggingFace
EMBEDDING_MODEL = "tfidf"
EMBEDDING_DIM = 384  # TF-IDF sẽ tự adjust dim theo vocabulary

VECTOR_STORE = "custom_json"


# =============================================================================
# IMPLEMENTATION
# =============================================================================

def load_documents() -> list[dict]:
    """
    Đọc toàn bộ markdown files từ data/standardized/.

    Returns:
        List of {'content': str, 'metadata': {'source': str, 'type': str}}
    """
    documents = []
    for md_file in sorted(STANDARDIZED_DIR.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        doc_type = "legal" if "legal" in str(md_file) else "news"
        documents.append({
            "content": content,
            "metadata": {
                "source": md_file.name,
                "type": doc_type,
                "path": str(md_file),
            }
        })
    return documents


def chunk_documents(documents: list[dict]) -> list[dict]:
    """
    Chunk documents theo RecursiveCharacterTextSplitter.

    Returns:
        List of {'content': str, 'metadata': dict}
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
        length_function=len,
    )

    chunks = []
    for doc in documents:
        splits = splitter.split_text(doc["content"])
        for i, chunk_text in enumerate(splits):
            chunks.append({
                "content": chunk_text,
                "metadata": {**doc["metadata"], "chunk_index": i}
            })
    return chunks


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Embed toàn bộ chunks bằng TF-IDF (sklearn).
    Offline, không cần download model.

    Returns:
        Mỗi chunk dict được thêm key 'embedding': list[float]
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    print(f"  Using TF-IDF embedding (offline mode)")
    texts = [c["content"] for c in chunks]

    vectorizer = TfidfVectorizer(
        max_features=EMBEDDING_DIM,
        ngram_range=(1, 2),   # unigrams + bigrams để bắt cụm từ tiếng Việt
        min_df=1,
        sublinear_tf=True,    # log(1+tf) để smooth TF
        analyzer="word",
    )
    tfidf_matrix = vectorizer.fit_transform(texts).toarray().astype(np.float32)

    # Lưu vectorizer để dùng lại cho query embedding
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    with open(VECTORIZER_FILE, "wb") as f:
        pickle.dump(vectorizer, f)

    for chunk, emb in zip(chunks, tfidf_matrix):
        chunk["embedding"] = emb.tolist()
    print(f"  ✓ TF-IDF matrix shape: {tfidf_matrix.shape}")
    return chunks


def index_to_vectorstore(chunks: list[dict]):
    """
    Lưu chunks vào custom JSON + numpy vector store tại data/vector_store/.
    """
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

    metadata_chunks = []
    embeddings_list = []

    for chunk in chunks:
        emb = chunk.pop("embedding", None)
        metadata_chunks.append(chunk)
        if emb is not None:
            embeddings_list.append(emb)

    # Lưu chunks (content + metadata) dưới dạng JSON
    CHUNKS_FILE.write_text(
        json.dumps(metadata_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Lưu embedding matrix dưới dạng numpy array
    if embeddings_list:
        embeddings_array = np.array(embeddings_list, dtype=np.float32)
        np.save(str(EMBEDDINGS_FILE), embeddings_array)
        print(f"  ✓ Saved {len(metadata_chunks)} chunks to {CHUNKS_FILE.name}")
        print(f"  ✓ Saved embeddings shape {embeddings_array.shape} to {EMBEDDINGS_FILE.name}")


def run_pipeline():
    """Chạy toàn bộ pipeline: load → chunk → embed → index."""
    print("=" * 50)
    print("Task 4: Chunking & Indexing")
    print(f"  Chunking: {CHUNKING_METHOD} (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    print(f"  Embedding: {EMBEDDING_MODEL}")
    print(f"  Vector Store: {VECTOR_STORE}")
    print("=" * 50)

    docs = load_documents()
    if not docs:
        print("⚠ Không có documents. Chạy Task 3 trước!")
        return

    print(f"\n✓ Loaded {len(docs)} documents")

    chunks = chunk_documents(docs)
    print(f"✓ Created {len(chunks)} chunks")

    chunks = embed_chunks(chunks)
    print(f"✓ Embedded {len(chunks)} chunks")

    index_to_vectorstore(chunks)
    print("✓ Indexed to vector store")


if __name__ == "__main__":
    run_pipeline()
