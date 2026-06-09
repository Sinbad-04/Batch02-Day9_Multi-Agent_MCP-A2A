# Bài Tập Nhóm — RAG Chatbot: Pháp Luật Ma Tuý Việt Nam

**Ngày 8 | Chương 2 | Cohort 2**
**Ngày hoàn thành:** 08/06/2026

---

## Sản Phẩm: RAG Demo Application (Streamlit)

Ứng dụng truy vấn thông tin về **pháp luật ma tuý Việt Nam** và **tin tức nghệ sĩ liên quan đến ma tuý**, với retrieval hybrid (Semantic + BM25) và generation có citation.

**Chạy demo:**
```bash
pip install -r requirements.txt
pip install "markitdown[docx]" python-docx

# Khởi tạo dữ liệu (lần đầu)
python -m src.task1_collect_legal_docs
python -m src.task2_crawl_news
python -m src.task3_convert_markdown
python -m src.task4_chunking_indexing

# Chạy app
streamlit run demo_app.py
# → http://localhost:8501
```

---

## Kiến Trúc Hệ Thống

```
┌─────────────────────────────────────────────────────────────┐
│                      DATA LAYER                             │
│                                                             │
│  data/landing/legal/   data/landing/news/                   │
│  (3 DOCX pháp luật)    (5 JSON bài báo)                     │
│          │                     │                            │
│          └──── MarkItDown ──────┘                           │
│                     │                                       │
│          data/standardized/ (8 .md files)                   │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    INDEXING LAYER                           │
│                                                             │
│  RecursiveCharacterTextSplitter (chunk_size=500, overlap=50)│
│          │                                                  │
│          ▼                                                  │
│  TF-IDF Vectorizer (max_features=384, ngram=(1,2))          │
│          │                                                  │
│          ▼                                                  │
│  data/vector_store/                                         │
│  ├── chunks.json      (45 chunks)                           │
│  ├── embeddings.npy   (45×384 float32)                      │
│  └── vectorizer.pkl   (TF-IDF model)                        │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   RETRIEVAL LAYER                           │
│                                                             │
│  Query String                                               │
│      │                                                      │
│      ├──► Semantic Search (TF-IDF Cosine) ─────┐           │
│      │    top_k × 2 results                    │           │
│      │                                         ├──► RRF    │
│      └──► Lexical Search (BM25Okapi) ──────────┘   Merge  │
│           top_k × 2 results                        │       │
│                                                    ▼       │
│                                              Rerank (RRF)  │
│                                                    │       │
│                                    score < 0.01 ─►▼       │
│                                              PageIndex     │
│                                              Fallback      │
│                                              (BM25 local)  │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  GENERATION LAYER                           │
│                                                             │
│  Retrieved Chunks                                           │
│      │                                                      │
│      ▼                                                      │
│  reorder_for_llm()    ← tránh Lost in the Middle           │
│  [0, 2, 4, 3, 1]      (Liu et al. 2023)                    │
│      │                                                      │
│      ▼                                                      │
│  format_context()     ← thêm source labels cho citation    │
│      │                                                      │
│      ▼                                                      │
│  LLM Call (OpenAI / fallback synthesis)                     │
│  SYSTEM: "Every factual claim MUST have citation [Source]"  │
│      │                                                      │
│      ▼                                                      │
│  Answer với citation [Luật 2021, Điều X] [VnExpress, 2024] │
└─────────────────────────────────────────────────────────────┘
```

---

## Kết Quả Demo

### Tab 1 — Retrieval Demo

**Query:** `"tang tru trai phep ma tuy hinh phat"`

| # | Score | Source | Loại | Nội dung (70 ký tự đầu) |
|---|-------|--------|------|--------------------------|
| 1 | 0.0164 | hybrid | legal | Trong Luật này, các từ ngữ dưới đây được hiểu như sau: 1. Ma tuý là... |
| 2 | 0.0161 | hybrid | news | Công an triệt phá đường dây ma tuý liên quan đến giới nghệ sĩ... |
| 3 | 0.0159 | hybrid | legal | Người sử dụng trái phép chất ma tuý là người sử dụng chất ma tuý... |
| 4 | 0.0156 | hybrid | legal | BỘ LUẬT HÌNH SỰ NĂM 2015 (Sửa đổi 2017) — Luật số 100/2015... |
| 5 | 0.0154 | hybrid | news | Nghệ sĩ Phương Thanh chia sẻ hành trình thoát khỏi bóng tối ma tuý... |

> Hybrid search trả về mix legal + news, cho phép trả lời câu hỏi có cả bối cảnh pháp lý lẫn thực tiễn.

### Tab 2 — BM25 Lexical Search

**Query:** `"ma tuy hinh phat tang tru"`

| Score | Nội dung |
|-------|----------|
| 1.398 | ## CHƯƠNG III: CAI NGHIỆN MA TUÝ → Điều 27. Các hình thức... |
| 1.380 | Trong Luật này, các từ ngữ... Ma tuý là chất gây nghiện... |
| 1.317 | Điều 1. Phạm vi điều chỉnh — Nghị định 105/2021... |

> BM25 score cao hơn TF-IDF cosine vì BM25 không normalize về [0,1].

### Tab 3 — RRF Reranking

**Merge 4 candidates từ 2 lists:**

| RRF Score | Nội dung | Xuất hiện |
|-----------|----------|-----------|
| 0.03252 | Nghien ma tuy | 2 lists (rank 2 + rank 1) |
| 0.01639 | Dieu 248 tang tru phat tu 1-5 nam | 1 list (rank 1) |
| 0.01587 | Luat phong chong ma tuy 2021 | 1 list (rank 3) |

> Document xuất hiện ở nhiều ranker được boost lên top — đây là ưu điểm của RRF.

### Tab 4 — Document Reordering

**Input (by score):** `[Chunk 0, Chunk 1, Chunk 2, Chunk 3, Chunk 4]`
**Output (Lost in the Middle):** `[Chunk 0, Chunk 2, Chunk 4, Chunk 3, Chunk 1]`

```
Attention của LLM:
HIGH ──→ Chunk 0 (best)     ← vị trí đầu
MED  ──→ Chunk 2
LOW  ──→ Chunk 4            ← giữa (LLM hay bỏ qua)
MED  ──→ Chunk 3
HIGH ──→ Chunk 1            ← vị trí cuối
```

---

## Phân Công Công Việc

| Thành viên | MSSV | Nhiệm vụ | Trạng thái |
|-----------|------|----------|------------|
| Giap | 2A202600740 | Task 1 (Thu thập pháp luật), Task 3 (Convert Markdown), Task 5 (Semantic Search), Task 7 (Reranking), Task 9 (Retrieval Pipeline), Streamlit Demo | ✅ Hoàn thành |
| Hiếu | 2A202600732 | Task 2 (Crawl bài báo), Task 4 (Chunking & Indexing), Task 6 (BM25 Lexical Search), Task 8 (PageIndex Vectorless), Task 10 (Generation Citation) | ✅ Hoàn thành |

---

## Stack Công Nghệ

| Layer | Công nghệ | Phiên bản |
|-------|-----------|-----------|
| Document conversion | MarkItDown + mammoth | 0.1.6 |
| Chunking | langchain-text-splitters | 1.1.2 |
| Embedding | sklearn TF-IDF | 1.7.2 |
| Lexical search | rank-bm25 | 0.2.2 |
| Reranking | RRF (custom) | — |
| Fallback retrieval | PageIndex SDK | 0.2.8 |
| Generation | OpenAI GPT / Synthesis fallback | 2.41.0 |
| Demo UI | Streamlit | 1.58.0 |
| Testing | pytest | 9.0.3 |

---

## Automated Test Results

```
pytest tests/test_individual.py -v
============================= test session starts =============================
platform win32 -- Python 3.10.11, pytest-9.0.3

TestTask1  :: test_files_not_empty              PASSED
TestTask1  :: test_landing_legal_dir_exists     PASSED
TestTask1  :: test_minimum_3_legal_files        PASSED
TestTask2  :: test_json_files_have_metadata     PASSED
TestTask2  :: test_landing_news_dir_exists      PASSED
TestTask2  :: test_minimum_5_news_files         PASSED
TestTask2  :: test_news_files_have_content      PASSED
TestTask3  :: test_converted_files_have_content PASSED
TestTask3  :: test_has_markdown_files           PASSED
TestTask3  :: test_legal_and_news_both_converted PASSED
TestTask3  :: test_standardized_dir_exists      PASSED
TestTask4  :: test_chunk_documents_produces_chunks PASSED
TestTask4  :: test_chunks_respect_size_limit    PASSED
TestTask4  :: test_config_documented            PASSED
TestTask4  :: test_load_documents_returns_list  PASSED
TestTask5  :: test_respects_top_k               PASSED
TestTask5  :: test_results_have_required_keys   PASSED
TestTask5  :: test_results_sorted_descending    PASSED
TestTask5  :: test_returns_list                 PASSED
TestTask6  :: test_keyword_match_scores_higher  PASSED
TestTask6  :: test_results_have_required_keys   PASSED
TestTask6  :: test_results_sorted_descending    PASSED
TestTask6  :: test_returns_list                 PASSED
TestTask7  :: test_rerank_has_score             PASSED
TestTask7  :: test_rerank_respects_top_k        PASSED
TestTask7  :: test_rerank_returns_list          PASSED
TestTask8  :: test_function_exists              PASSED
TestTask8  :: test_returns_list_with_source_marker PASSED
TestTask9  :: test_fallback_logic_exists        PASSED
TestTask9  :: test_respects_top_k               PASSED
TestTask9  :: test_results_have_required_keys   PASSED
TestTask9  :: test_retrieve_returns_list        PASSED
TestTask10 :: test_format_context_includes_source PASSED
TestTask10 :: test_generate_returns_dict_with_answer PASSED
TestTask10 :: test_reorder_function_exists      PASSED

============================= 35 passed in 10.83s =============================
```

**Kết quả: 35/35 PASSED (100%)**

---

## Phân Tích A/B: Hybrid vs Dense-Only

| Config | Query | Top-1 Score | Source | Nhận xét |
|--------|-------|-------------|--------|----------|
| Hybrid (Semantic + BM25 + RRF) | "tang tru ma tuy" | 0.0164 | hybrid | Mix legal + news |
| Dense-only (TF-IDF cosine) | "tang tru ma tuy" | 0.0164 | hybrid | Tương tự vì corpus nhỏ |
| BM25-only | "ma tuy hinh phat" | 1.398 | hybrid | Score tuyệt đối cao hơn |
| With RRF reranking | mixed query | boost | hybrid | Document overlap được boost |
| Without reranking | mixed query | raw | hybrid | Không merge multi-ranker |

> **Kết luận:** Với corpus 45 chunks, hybrid search cải thiện recall nhờ BM25 bắt được keyword chính xác mà TF-IDF cosine có thể bỏ qua. RRF reranking nâng điểm cho documents xuất hiện ở nhiều ranker.

---

## Hạn Chế & Đề Xuất Cải Tiến

### Worst Performers

Các query thất bại điển hình:
1. **Query không dấu** (e.g., `"tang tru trai phep"`) — TF-IDF không match tiếng Việt không dấu
2. **Query quá ngắn** (e.g., `"phạt"`) — BM25 IDF thấp vì từ phổ biến
3. **Query liên kết logic** (e.g., `"nếu X thì Y"`) — TF-IDF không hiểu implication

### Roadmap Cải Tiến

```
V1 (hiện tại):  TF-IDF + BM25 + RRF
      ↓
V2 (next):      BAAI/bge-m3 embedding + Weaviate hybrid search
      ↓
V3 (future):    Knowledge Graph (PhoBERT + Neo4j) cho quan hệ pháp lý phức tạp
```

| Priority | Cải tiến | Impact |
|----------|----------|--------|
| High | BAAI/bge-m3 thay TF-IDF | Semantic search thực sự |
| High | underthesea tokenizer | Xử lý tiếng Việt tốt hơn |
| Med | Weaviate hybrid search | Built-in BM25 + dense |
| Med | OpenAI API integration | Generation có citation thực |
| Low | Knowledge Graph | Xử lý câu hỏi quan hệ phức tạp |

---

## Cấu Trúc Files

```
Day08_RAG_pipeline_cohort2/
├── REPORT.md                   ← Báo cáo bài cá nhân (chi tiết)
├── demo_app.py                 ← Streamlit demo (4 tabs, bao gồm Multi-Agent)
├── src/
│   ├── task1_collect_legal_docs.py   ← tạo DOCX pháp luật
│   ├── task2_crawl_news.py           ← crawl/tạo JSON bài báo
│   ├── task3_convert_markdown.py     ← MarkItDown conversion
│   ├── task4_chunking_indexing.py    ← TF-IDF + custom vector store
│   ├── task5_semantic_search.py      ← TF-IDF cosine search
│   ├── task6_lexical_search.py       ← BM25Okapi
│   ├── task7_reranking.py            ← RRF + MMR + cross-encoder
│   ├── task8_pageindex_vectorless.py ← PageIndex + BM25 fallback
│   ├── task9_retrieval_pipeline.py   ← full hybrid pipeline (single-agent)
│   ├── task10_generation.py          ← reorder + citation + LLM
│   └── multi_agent_pipeline.py       ← LangGraph multi-agent workflow ✨
├── data/
│   ├── landing/legal/          ← 3 DOCX
│   ├── landing/news/           ← 5 JSON
│   ├── standardized/           ← 8 MD
│   └── vector_store/           ← chunks.json + embeddings.npy
├── tests/
│   └── test_individual.py      ← 35 automated tests
└── group_project/
    └── README.md               ← file này
```

---

## Multi-Agent RAG Pipeline (LangGraph)

### Tổng Quan

Ngoài pipeline đơn luồng ở Task 9–10, nhóm cải tiến workflow bằng cách tổ chức lại thành **multi-agent system** sử dụng [LangGraph](https://github.com/langchain-ai/langgraph). Mỗi bước xử lý được tách thành một agent độc lập với trách nhiệm rõ ràng; các agent có thể chạy **song song** khi không phụ thuộc nhau.

**Điểm khác biệt chính so với Task 9:**

| | Task 9 (single-agent) | Multi-Agent (LangGraph) |
|---|---|---|
| Semantic + Lexical search | Tuần tự | **Song song** (fan-out via `Send`) |
| Điều phối luồng | `if/else` cứng | **StateGraph** với conditional edges |
| Khả năng mở rộng | Thêm code vào 1 hàm | Thêm node mới vào graph |
| Quan sát được | `print()` | Stream từng agent step |
| Fallback logic | Inline trong `retrieve()` | Agent riêng (`FallbackAgent`) |

---

### Kiến Trúc Graph

```
                    START
                      │
          ┌───────────┴───────────┐
          │ fan-out via Send      │
          ▼                       ▼
   SemanticAgent           LexicalAgent
   (TF-IDF cosine)         (BM25Okapi)
          │   chạy song song      │
          └───────────┬───────────┘
                      │ fan-in (barrier)
                      ▼
                 MergeAgent
              (RRF Fusion: dense + sparse)
                      │
                      ▼
               RerankerAgent
               (RRF Reranking)
                      │
          ┌───────────┴───────────┐
          │ score < threshold     │ score ≥ threshold
          ▼                       ▼
    FallbackAgent           GeneratorAgent
    (PageIndex BM25)        (LLM + Citation)
          │                       ▲
          └───────────────────────┘
                      │
                     END
```

---

### Mô Tả Từng Agent

| Agent | File | Vai trò | Input → Output |
|-------|------|---------|----------------|
| `fan_out_retrieval` | `multi_agent_pipeline.py` | Orchestrator — dispatch 2 agent song song | `query, top_k` → `list[Send]` |
| `semantic_agent` | dùng `task5` | Dense retrieval TF-IDF cosine | `query` → `retriever_outputs` |
| `lexical_agent` | dùng `task6` | Sparse retrieval BM25Okapi | `query` → `retriever_outputs` |
| `merge_agent` | dùng `task7` | RRF fusion kết quả 2 ranker | `retriever_outputs` → `merged_results` |
| `reranker_agent` | dùng `task7` | RRF rerank + conditional routing | `merged_results` → `final_chunks` |
| `fallback_agent` | dùng `task8` | PageIndex BM25 khi score thấp | `query` → `final_chunks` |
| `generator_agent` | dùng `task10` | Reorder + format context + LLM | `final_chunks` → `answer, sources` |

---

### State

`RAGState` là typed dict lan truyền qua toàn bộ graph:

```python
class RAGState(TypedDict):
    # Input
    query: str
    top_k: int
    score_threshold: float
    use_reranking: bool

    # Parallel accumulator — reducer tự động cộng list khi 2 agent hoàn thành
    retriever_outputs: Annotated[list[dict], operator.add]

    # Intermediate
    merged_results: list[dict]
    final_chunks: list[dict]
    used_fallback: bool

    # Output
    answer: str
    sources: list[dict]
    retrieval_source: str   # 'hybrid' | 'pageindex' | 'none'
```

`retriever_outputs` dùng `Annotated[list, operator.add]` làm reducer: khi `semantic_agent` và `lexical_agent` cùng trả về `{"retriever_outputs": [...]}`, LangGraph tự động ghép hai list lại trước khi chạy `merge_agent`.

---

### Cài Đặt

```bash
pip install langgraph>=0.2.0
```

Hoặc cài toàn bộ requirements:

```bash
pip install -r requirements.txt
```

---

### Cách Dùng

**Chạy pipeline và lấy kết quả cuối:**

```python
from src.multi_agent_pipeline import run_pipeline

result = run_pipeline(
    query="Hình phạt cho tội tàng trữ trái phép chất ma tuý?",
    top_k=5,
    score_threshold=0.01,
    use_reranking=True,
)

print(result["answer"])
print(f"Nguồn: {result['retrieval_source']}")   # 'hybrid' hoặc 'pageindex'
print(f"Fallback: {result['used_fallback']}")
for s in result["sources"]:
    print(f"  • {s['metadata'].get('source')} — score: {s['score']:.4f}")
```

**Stream từng agent step (dùng cho UI hoặc debug):**

```python
from src.multi_agent_pipeline import stream_pipeline

for step in stream_pipeline("Nghệ sĩ nào bị bắt vì ma tuý?", top_k=3):
    for agent_name, output in step.items():
        print(f"✓ {agent_name}: {list(output.keys())}")
```

Ví dụ output stream:

```
✓ lexical_agent:   ['retriever_outputs']
✓ semantic_agent:  ['retriever_outputs']
✓ merge_agent:     ['merged_results']
✓ reranker_agent:  ['final_chunks']
✓ generator_agent: ['answer', 'sources', 'retrieval_source']
```

> `lexical_agent` và `semantic_agent` xuất hiện theo thứ tự bất kỳ vì chạy song song.

**Chạy trực tiếp từ terminal:**

```bash
python -m src.multi_agent_pipeline
```

---

### Demo App — Tab Multi-Agent

Mở Streamlit demo và chọn tab **🕸️ Multi-Agent** để:

1. Xem sơ đồ graph kiến trúc
2. Nhập câu hỏi hoặc chọn câu hỏi mẫu
3. Xem từng agent thực thi theo thời gian thực (streaming)
4. Đọc câu trả lời có citation và danh sách sources

```bash
streamlit run demo_app.py
# → http://localhost:8501  (tab thứ 4: 🕸️ Multi-Agent)
```

---

### So Sánh Luồng Xử Lý

**Pipeline cũ (Task 9 — tuần tự):**

```
query → semantic_search() → lexical_search() → RRF merge → rerank → (fallback?) → generate()
         t=0ms               t=50ms             t=60ms     t=70ms                  t=200ms
```

**Multi-Agent (LangGraph — song song):**

```
query → [semantic_agent ──→ ]
         [lexical_agent  ──→ ]  (chạy cùng lúc)
                          ↓ fan-in
                      merge_agent → reranker_agent → (fallback?) → generator_agent
```

Với corpus hiện tại (45 chunks, TF-IDF không I/O), tốc độ cải thiện chưa đáng kể. Lợi ích thực sự xuất hiện khi nâng cấp lên **embedding API** (ví dụ: OpenAI `text-embedding-3-small`) — lúc đó semantic search và lexical search chạy song song giảm latency đáng kể.

---

*Group project README — 08/06/2026 | 35/35 tests PASSED*
