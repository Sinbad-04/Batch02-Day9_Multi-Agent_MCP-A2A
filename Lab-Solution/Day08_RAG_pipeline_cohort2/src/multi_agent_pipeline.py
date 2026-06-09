"""
Multi-Agent RAG Pipeline với LangGraph.

Kiến trúc:
    START
     │ fan-out via Send (parallel)
     ├──────────────────────────┐
     ▼                          ▼
SemanticAgent            LexicalAgent
(TF-IDF cosine)          (BM25Okapi)
     │                          │
     └──────────┬───────────────┘
                ▼ fan-in
           MergeAgent  (RRF fusion)
                │
                ▼
          RerankerAgent  (RRF rerank)
                │
     ┌──────────┴──────────┐
     ▼ score < threshold   ▼ score ≥ threshold
FallbackAgent        GeneratorAgent (LLM + citation)
(PageIndex BM25)           ▲
     │                     │
     └─────────────────────┘
                │
               END
"""

import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .task5_semantic_search import semantic_search
from .task6_lexical_search import lexical_search
from .task7_reranking import rerank, rerank_rrf
from .task8_pageindex_vectorless import pageindex_search
from .task10_generation import (
    SYSTEM_PROMPT,
    TEMPERATURE,
    TOP_P,
    _synthesize_without_llm,
    format_context,
    reorder_for_llm,
)


# =============================================================================
# STATE
# =============================================================================

class RAGState(TypedDict):
    # Input
    query: str
    top_k: int
    score_threshold: float
    use_reranking: bool

    # Parallel retrieval accumulator — reducer adds lists together
    retriever_outputs: Annotated[list[dict], operator.add]

    # Intermediate
    merged_results: list[dict]
    final_chunks: list[dict]
    used_fallback: bool

    # Output
    answer: str
    sources: list[dict]
    retrieval_source: str


# =============================================================================
# NODES
# =============================================================================

def fan_out_retrieval(state: RAGState) -> list[Send]:
    """OrchestratorAgent: dispatch semantic + lexical search in parallel via Send."""
    base = {
        "query": state["query"],
        "top_k": state["top_k"],
        "retriever_outputs": [],
    }
    return [Send("semantic_agent", base), Send("lexical_agent", base)]


def semantic_agent(state: RAGState) -> dict:
    """SemanticAgent: TF-IDF cosine similarity dense retrieval."""
    results = semantic_search(state["query"], top_k=state["top_k"] * 2)
    return {"retriever_outputs": [{"agent_type": "semantic", "results": results}]}


def lexical_agent(state: RAGState) -> dict:
    """LexicalAgent: BM25Okapi sparse keyword retrieval."""
    results = lexical_search(state["query"], top_k=state["top_k"] * 2)
    return {"retriever_outputs": [{"agent_type": "lexical", "results": results}]}


def merge_agent(state: RAGState) -> dict:
    """MergeAgent: RRF fusion of dense + sparse results from parallel agents."""
    dense = next(
        (o["results"] for o in state["retriever_outputs"] if o["agent_type"] == "semantic"),
        [],
    )
    sparse = next(
        (o["results"] for o in state["retriever_outputs"] if o["agent_type"] == "lexical"),
        [],
    )
    lists = [lst for lst in [dense, sparse] if lst]
    if lists:
        merged = rerank_rrf(lists, top_k=state["top_k"] * 2)
        for item in merged:
            item["source"] = "hybrid"
    else:
        merged = []
    return {"merged_results": merged}


def reranker_agent(state: RAGState) -> dict:
    """RerankerAgent: RRF reranking on merged candidates."""
    merged = state["merged_results"]
    if state.get("use_reranking", True) and merged:
        final = rerank(state["query"], merged, top_k=state["top_k"])
    else:
        final = merged[: state["top_k"]]
    return {"final_chunks": final}


def fallback_agent(state: RAGState) -> dict:
    """FallbackAgent: PageIndex BM25 when hybrid score is below threshold."""
    results = pageindex_search(state["query"], top_k=state["top_k"])
    return {"final_chunks": results, "used_fallback": True}


def generator_agent(state: RAGState) -> dict:
    """GeneratorAgent: reorder → format context → LLM call with inline citations."""
    import os

    from dotenv import load_dotenv

    load_dotenv()

    chunks = state["final_chunks"]
    if not chunks:
        return {
            "answer": "Tôi không thể xác minh thông tin này từ nguồn hiện có.",
            "sources": [],
            "retrieval_source": "none",
        }

    reordered = reorder_for_llm(chunks)
    context = format_context(reordered)
    user_message = f"Context:\n{context}\n\n---\n\nCâu hỏi: {state['query']}"
    retrieval_source = (
        "pageindex" if state.get("used_fallback") else chunks[0].get("source", "hybrid")
    )

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        answer = _synthesize_without_llm(state["query"], reordered)
    else:
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


# =============================================================================
# ROUTING
# =============================================================================

def route_after_reranker(
    state: RAGState,
) -> Literal["fallback_agent", "generator_agent"]:
    """Conditional edge: fallback if best score < threshold, else generate."""
    final = state.get("final_chunks", [])
    best_score = final[0]["score"] if final else 0.0
    if not final or best_score < state["score_threshold"]:
        return "fallback_agent"
    return "generator_agent"


# =============================================================================
# GRAPH
# =============================================================================

def build_graph():
    g = StateGraph(RAGState)

    g.add_node("semantic_agent", semantic_agent)
    g.add_node("lexical_agent", lexical_agent)
    g.add_node("merge_agent", merge_agent)
    g.add_node("reranker_agent", reranker_agent)
    g.add_node("fallback_agent", fallback_agent)
    g.add_node("generator_agent", generator_agent)

    # START → parallel fan-out via Send
    g.add_conditional_edges(START, fan_out_retrieval, ["semantic_agent", "lexical_agent"])

    # Fan-in: both retrieval agents must complete before merge
    g.add_edge("semantic_agent", "merge_agent")
    g.add_edge("lexical_agent", "merge_agent")

    g.add_edge("merge_agent", "reranker_agent")

    # Conditional: fallback or generate
    g.add_conditional_edges(
        "reranker_agent",
        route_after_reranker,
        {"fallback_agent": "fallback_agent", "generator_agent": "generator_agent"},
    )

    # Fallback feeds into generator
    g.add_edge("fallback_agent", "generator_agent")
    g.add_edge("generator_agent", END)

    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# =============================================================================
# PUBLIC API
# =============================================================================

_INITIAL_STATE = {
    "retriever_outputs": [],
    "merged_results": [],
    "final_chunks": [],
    "used_fallback": False,
    "answer": "",
    "sources": [],
    "retrieval_source": "hybrid",
}


def run_pipeline(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.01,
    use_reranking: bool = True,
) -> dict:
    """
    Run the full multi-agent RAG pipeline and return the final result.

    Returns:
        {
            'answer': str,
            'sources': list[dict],
            'retrieval_source': str,  # 'hybrid' | 'pageindex' | 'none'
            'used_fallback': bool,
        }
    """
    result = get_graph().invoke({
        **_INITIAL_STATE,
        "query": query,
        "top_k": top_k,
        "score_threshold": score_threshold,
        "use_reranking": use_reranking,
    })
    return {
        "answer": result.get("answer", ""),
        "sources": result.get("sources", []),
        "retrieval_source": result.get("retrieval_source", "unknown"),
        "used_fallback": result.get("used_fallback", False),
    }


def stream_pipeline(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.01,
    use_reranking: bool = True,
):
    """
    Stream multi-agent pipeline execution step-by-step.

    Yields:
        dict of {agent_name: agent_output} for each completed agent.
    """
    yield from get_graph().stream(
        {
            **_INITIAL_STATE,
            "query": query,
            "top_k": top_k,
            "score_threshold": score_threshold,
            "use_reranking": use_reranking,
        },
        stream_mode="updates",
    )


if __name__ == "__main__":
    test_queries = [
        "Hình phạt cho tội tàng trữ trái phép chất ma tuý?",
        "Nghệ sĩ nào bị bắt vì sử dụng ma tuý?",
    ]

    for q in test_queries:
        print(f"\n{'='*70}")
        print(f"Q: {q}")
        print("=" * 70)

        print("\n[Agent steps]")
        final_answer = ""
        for step in stream_pipeline(q):
            for agent_name, output in step.items():
                active_keys = [k for k, v in output.items() if v]
                print(f"  ✓ {agent_name}: {active_keys}")
                if agent_name == "generator_agent":
                    final_answer = output.get("answer", "")

        print(f"\nA: {final_answer[:200]}...")
