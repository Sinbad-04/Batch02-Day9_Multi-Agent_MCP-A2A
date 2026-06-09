"""
Demo Streamlit — RAG Pipeline v2
Chủ đề: Pháp luật Việt Nam về ma tuý + Tin tức nghệ sĩ liên quan đến ma tuý
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# ─────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RAG Pipeline Demo — Pháp Luật Ma Tuý",
    page_icon="⚖️",
    layout="wide",
)

st.title("⚖️ RAG Pipeline Demo")
st.caption("Truy vấn thông tin về pháp luật ma tuý Việt Nam và tin tức nghệ sĩ liên quan")

# ─────────────────────────────────────────────────────────
# SIDEBAR — Pipeline overview
# ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📐 Kiến Trúc Pipeline")
    st.markdown("""
    ```
    Query
     ├→ Semantic Search (TF-IDF)
     ├→ Lexical Search (BM25)
     ├→ RRF Merge
     ├→ Rerank (RRF)
     └→ Fallback PageIndex
    ```
    """)
    st.divider()
    st.header("📚 Nguồn Dữ Liệu")
    st.markdown("""
    **Pháp luật:**
    - Luật Phòng chống ma tuý 2021
    - Nghị định 105/2021/NĐ-CP
    - Bộ luật Hình sự — Chương XX

    **Tin tức:**
    - 5 bài báo về nghệ sĩ liên quan ma tuý
    """)
    st.divider()
    st.header("⚙️ Cấu Hình")
    top_k = st.slider("top_k (số chunks trả về)", 1, 10, 5)
    score_threshold = st.slider("Score threshold (fallback)", 0.0, 1.0, 0.01, 0.01)
    use_reranking = st.checkbox("Dùng Reranking (RRF)", value=True)

# ─────────────────────────────────────────────────────────
# LOAD PIPELINE
# ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Đang tải RAG pipeline...")
def load_pipeline():
    from src.task9_retrieval_pipeline import retrieve
    from src.task10_generation import generate_with_citation, reorder_for_llm, format_context
    return retrieve, generate_with_citation, reorder_for_llm, format_context

try:
    retrieve, generate_with_citation, reorder_for_llm, format_context = load_pipeline()
    pipeline_ok = True
except Exception as e:
    st.error(f"Lỗi load pipeline: {e}")
    pipeline_ok = False

# ─────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🔍 Retrieval Demo", "🤖 Generation Demo", "📊 Thống Kê", "🕸️ Multi-Agent"])

# ─────────────────────────────────────────────────────────
# TAB 1 — RETRIEVAL
# ─────────────────────────────────────────────────────────
with tab1:
    st.subheader("Retrieval Pipeline (Task 5 + 6 + 7 + 8 + 9)")

    SAMPLE_QUERIES = [
        "Hình phạt tàng trữ trái phép chất ma tuý là gì?",
        "Điều 248 Bộ luật Hình sự quy định thế nào?",
        "Nghệ sĩ nào bị bắt vì liên quan đến ma tuý?",
        "Quy trình cai nghiện ma tuý tự nguyện tại gia đình",
        "Mức phạt tử hình áp dụng khi nào?",
    ]

    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Nhập câu hỏi:", placeholder="Ví dụ: Hình phạt tàng trữ ma tuý?")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        selected = st.selectbox("Câu hỏi mẫu:", ["— chọn —"] + SAMPLE_QUERIES, label_visibility="collapsed")
        if selected != "— chọn —":
            query = selected

    if st.button("🔍 Tìm Kiếm", type="primary", disabled=not pipeline_ok or not query):
        with st.spinner("Đang tìm kiếm..."):
            import time
            t0 = time.time()
            results = retrieve(query, top_k=top_k, score_threshold=score_threshold,
                               use_reranking=use_reranking)
            elapsed = time.time() - t0

        st.success(f"Tìm thấy **{len(results)}** kết quả trong **{elapsed:.2f}s**")

        for i, r in enumerate(results, 1):
            source_badge = "🔵 hybrid" if r.get("source") == "hybrid" else "🟡 pageindex"
            doc_type = r.get("metadata", {}).get("type", "unknown")
            type_badge = "📜 legal" if doc_type == "legal" else "📰 news"
            src_name = r.get("metadata", {}).get("source", "N/A")
            score = r.get("score", 0)

            with st.expander(
                f"**#{i}** {type_badge} {source_badge} | Score: `{score:.4f}` | {src_name}",
                expanded=(i == 1),
            ):
                st.markdown(r["content"])

# ─────────────────────────────────────────────────────────
# TAB 2 — GENERATION
# ─────────────────────────────────────────────────────────
with tab2:
    st.subheader("Generation với Citation (Task 10)")

    GEN_SAMPLES = [
        "Hình phạt cho tội tàng trữ trái phép chất ma tuý theo pháp luật Việt Nam?",
        "Các hình thức cai nghiện ma tuý được quy định như thế nào?",
        "Nghệ sĩ Châu Việt Cường bị xử lý thế nào?",
        "Hành vi tổ chức sử dụng ma tuý bị phạt bao nhiêu năm tù?",
    ]

    gen_query = st.text_input("Câu hỏi để generate:", key="gen_query",
                               placeholder="Nhập câu hỏi cần trả lời chi tiết...")
    gen_selected = st.selectbox("Câu hỏi mẫu:", ["— chọn —"] + GEN_SAMPLES, key="gen_sel")
    if gen_selected != "— chọn —":
        gen_query = gen_selected

    col_a, col_b = st.columns(2)
    with col_a:
        show_reorder = st.checkbox("Hiển thị Document Reordering", value=True)
    with col_b:
        show_context = st.checkbox("Hiển thị Context Format", value=False)

    if st.button("🤖 Generate", type="primary", disabled=not pipeline_ok or not gen_query):
        with st.spinner("Đang retrieve và generate..."):
            import time
            t0 = time.time()
            result = generate_with_citation(gen_query, top_k=top_k)
            elapsed = time.time() - t0

        st.success(f"Hoàn thành trong **{elapsed:.2f}s** | Nguồn: **{result['retrieval_source']}**")

        st.markdown("### 📝 Câu Trả Lời")
        st.markdown(result["answer"])

        if show_reorder and result["sources"]:
            st.markdown("---")
            st.markdown("### 🔀 Document Reordering (tránh Lost in the Middle)")
            chunks = result["sources"]
            reordered = reorder_for_llm(chunks)
            cols = st.columns(len(chunks))
            orig_indices = {id(c): i+1 for i, c in enumerate(chunks)}
            for col, chunk in zip(cols, reordered):
                orig_pos = orig_indices.get(id(chunk), "?")
                score = chunk.get("score", 0)
                col.metric(f"Vị trí gốc #{orig_pos}", f"Score: {score:.3f}")

        if show_context and result["sources"]:
            st.markdown("---")
            st.markdown("### 📄 Formatted Context")
            st.code(format_context(result["sources"]), language="markdown")

        st.markdown("---")
        st.markdown(f"**Sources sử dụng:** {len(result['sources'])} chunks")
        for s in result["sources"]:
            meta = s.get("metadata", {})
            st.caption(f"• {meta.get('source', 'N/A')} ({meta.get('type', 'unknown')}) — score: {s.get('score', 0):.4f}")

# ─────────────────────────────────────────────────────────
# TAB 3 — STATS
# ─────────────────────────────────────────────────────────
with tab3:
    st.subheader("📊 Thống Kê Vector Store & Dữ Liệu")

    col1, col2, col3 = st.columns(3)

    from pathlib import Path
    import json

    VECTOR_STORE_DIR = Path("data/vector_store")
    LANDING_LEGAL = Path("data/landing/legal")
    LANDING_NEWS = Path("data/landing/news")
    STANDARDIZED = Path("data/standardized")

    legal_files = list(LANDING_LEGAL.glob("*.docx")) + list(LANDING_LEGAL.glob("*.pdf"))
    news_files = list(LANDING_NEWS.glob("*.json"))
    md_files = list(STANDARDIZED.rglob("*.md"))

    with col1:
        st.metric("📜 Văn bản pháp luật", len(legal_files))
        st.metric("📰 Bài báo crawled", len(news_files))

    with col2:
        st.metric("📝 Files Markdown", len(md_files))
        chunks_file = VECTOR_STORE_DIR / "chunks.json"
        if chunks_file.exists():
            chunks = json.loads(chunks_file.read_text(encoding="utf-8"))
            st.metric("🧩 Chunks indexed", len(chunks))
        else:
            st.metric("🧩 Chunks indexed", "0 (chưa build)")

    with col3:
        emb_file = VECTOR_STORE_DIR / "embeddings.npy"
        if emb_file.exists():
            import numpy as np
            emb = np.load(str(emb_file))
            st.metric("📐 Embedding shape", f"{emb.shape[0]}×{emb.shape[1]}")
            st.metric("💾 Index size", f"{emb_file.stat().st_size/1024:.1f} KB")
        else:
            st.metric("📐 Embedding", "N/A")

    st.divider()

    st.markdown("### 🔧 Task Completion Status")
    tasks = [
        ("Task 1", "Thu thập văn bản pháp luật", len(legal_files) >= 3, f"{len(legal_files)} DOCX files"),
        ("Task 2", "Crawl bài báo", len(news_files) >= 5, f"{len(news_files)} JSON files"),
        ("Task 3", "Convert Markdown", len(md_files) >= 1, f"{len(md_files)} .md files"),
        ("Task 4", "Chunking & Indexing", chunks_file.exists(), "TF-IDF vector store"),
        ("Task 5", "Semantic Search", chunks_file.exists(), "TF-IDF cosine similarity"),
        ("Task 6", "Lexical Search (BM25)", True, "BM25Okapi lazy loading"),
        ("Task 7", "Reranking", True, "RRF (Reciprocal Rank Fusion)"),
        ("Task 8", "PageIndex Vectorless", True, "BM25 fallback khi không có API key"),
        ("Task 9", "Retrieval Pipeline", True, "Hybrid + fallback logic"),
        ("Task 10", "Generation với Citation", True, "Reorder + format + LLM call"),
    ]

    for task_id, name, done, detail in tasks:
        col_a, col_b, col_c = st.columns([1, 3, 4])
        with col_a:
            st.markdown(f"**{task_id}**")
        with col_b:
            st.markdown(f"{'✅' if done else '❌'} {name}")
        with col_c:
            st.caption(detail)

    st.divider()
    st.markdown("### 📁 Cấu Trúc Thư Mục")

    st.code("""
data/
├── landing/
│   ├── legal/          ← 3 DOCX pháp luật
│   └── news/           ← 5 JSON bài báo
├── standardized/
│   ├── legal/          ← 3 .md (MarkItDown)
│   └── news/           ← 5 .md
└── vector_store/
    ├── chunks.json     ← 45 chunks
    ├── embeddings.npy  ← TF-IDF matrix (45×384)
    └── vectorizer.pkl  ← TF-IDF vectorizer
    """, language="text")

# ─────────────────────────────────────────────────────────
# TAB 4 — MULTI-AGENT (LangGraph)
# ─────────────────────────────────────────────────────────
with tab4:
    st.subheader("🕸️ Multi-Agent RAG Pipeline (LangGraph)")

    _AGENT_LABELS = {
        "semantic_agent":  ("🔵", "SemanticAgent",  "TF-IDF cosine similarity"),
        "lexical_agent":   ("🟢", "LexicalAgent",   "BM25Okapi keyword search"),
        "merge_agent":     ("🟡", "MergeAgent",     "RRF fusion (dense + sparse)"),
        "reranker_agent":  ("🟠", "RerankerAgent",  "RRF reranking"),
        "fallback_agent":  ("🔴", "FallbackAgent",  "PageIndex BM25 fallback"),
        "generator_agent": ("🤖", "GeneratorAgent", "LLM generation with citation"),
    }

    col_graph, col_query = st.columns([1, 1])

    with col_graph:
        st.markdown("#### Kiến Trúc Graph")
        st.code("""
START
  │ (fan-out via Send)
  ├──────────────────────┐
  ▼                      ▼
SemanticAgent        LexicalAgent
(TF-IDF cosine)      (BM25Okapi)
  │ parallel             │ parallel
  └──────────┬───────────┘
             ▼ (fan-in)
         MergeAgent
         (RRF Fusion)
             │
             ▼
        RerankerAgent
        (RRF Rerank)
             │
    ┌────────┴─────────┐
    ▼ score<threshold  ▼ score≥threshold
FallbackAgent    GeneratorAgent
(PageIndex)      (LLM+Citation)
    │                  ▲
    └──────────────────┘
             │
            END
        """, language="text")

    with col_query:
        st.markdown("#### Agents")
        for icon, name, desc in _AGENT_LABELS.values():
            st.markdown(f"{icon} **{name}** — {desc}")

    st.divider()

    MA_SAMPLES = [
        "Hình phạt cho tội tàng trữ trái phép chất ma tuý?",
        "Nghệ sĩ nào bị bắt vì liên quan đến ma tuý?",
        "Điều 248 Bộ luật Hình sự quy định thế nào?",
        "Quy trình cai nghiện ma tuý tự nguyện tại gia đình?",
    ]

    ma_col1, ma_col2 = st.columns([3, 1])
    with ma_col1:
        ma_query = st.text_input("Câu hỏi:", key="ma_query",
                                  placeholder="Ví dụ: Hình phạt tàng trữ ma tuý?")
    with ma_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        ma_sel = st.selectbox("Câu hỏi mẫu:", ["— chọn —"] + MA_SAMPLES,
                               key="ma_sel", label_visibility="collapsed")
        if ma_sel != "— chọn —":
            ma_query = ma_sel

    if st.button("🕸️ Chạy Multi-Agent Pipeline", type="primary",
                 disabled=not pipeline_ok or not ma_query):
        try:
            from src.multi_agent_pipeline import stream_pipeline
        except ImportError as e:
            st.error(f"Cần cài langgraph: `pip install langgraph>=0.2.0`\n\n{e}")
            st.stop()

        import time

        t0 = time.time()
        completed_steps: list[tuple[str, dict]] = []

        st.markdown("### 🔄 Agent Execution")
        with st.status("Đang chạy agents...", expanded=True) as status:
            for step in stream_pipeline(
                ma_query,
                top_k=top_k,
                score_threshold=score_threshold,
                use_reranking=use_reranking,
            ):
                for agent_name, output in step.items():
                    icon, label, desc = _AGENT_LABELS.get(
                        agent_name, ("⚙️", agent_name, "")
                    )
                    active_keys = [k for k, v in output.items() if v]
                    st.write(f"{icon} **{label}** → `{active_keys}`")
                    completed_steps.append((agent_name, output))
            status.update(label="✅ Hoàn thành!", state="complete")

        elapsed = time.time() - t0

        # Extract final outputs
        gen_out = next((out for name, out in completed_steps if name == "generator_agent"), {})
        used_fallback = any(name == "fallback_agent" for name, _ in completed_steps)
        answer = gen_out.get("answer", "")
        sources = gen_out.get("sources", [])
        retrieval_source = gen_out.get("retrieval_source", "unknown")

        source_badge = "🔴 pageindex (fallback)" if used_fallback else "🔵 hybrid"
        agent_count = len(completed_steps)
        st.success(
            f"Hoàn thành trong **{elapsed:.2f}s** | "
            f"**{agent_count}** agents | Nguồn: **{source_badge}**"
        )

        st.markdown("### 📝 Câu Trả Lời")
        st.markdown(answer if answer else "_Không có kết quả._")

        if sources:
            st.markdown("---")
            st.markdown(f"**Sources:** {len(sources)} chunks")
            for s in sources:
                meta = s.get("metadata", {})
                st.caption(
                    f"• {meta.get('source', 'N/A')} "
                    f"({meta.get('type', 'unknown')}) — "
                    f"score: {s.get('score', 0):.4f}"
                )
