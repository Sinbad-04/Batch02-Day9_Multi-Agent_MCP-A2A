# Lab Assignment — Batch02 Day 9: Multi-Agent, MCP & A2A

**Ngày:** 2026-06-09  
**Môn:** Multi-Agent Systems, MCP, Agent-to-Agent (A2A) Protocol  
**Dự án:** Legal Multi-Agent System

---

## Tổng Quan Hệ Thống

Hệ thống tư vấn pháp lý đa tầng, xây dựng qua 5 stages từ đơn giản đến phức tạp:

```
Stage 1 → Stage 2 → Stage 3 → Stage 4 → Stage 5 (A2A)
Direct     RAG +     ReAct     Multi-     Distributed
LLM        Tools     Agent     Agent      Services
```

---

## Stage 1 — Direct LLM Calling

**File:** `stages/stage_1_direct_llm/main.py`

Gọi LLM trực tiếp, không tools, không memory. Trả lời từ training data.

```python
llm = get_llm()
messages = [
    SystemMessage(content="You are a legal expert..."),
    HumanMessage(content=question),
]
response = await llm.ainvoke(messages)
```

**Giới hạn:**
- Stateless — không nhớ hội thoại trước
- Không dùng được tools hay database
- Có thể hallucinate vì không có grounding

---

## Stage 2 — LLM + RAG / Tools

**File:** `stages/stage_2_rag_tools/main.py`

Gắn tools vào LLM, thực thi thủ công vòng lặp tool call.

**Tools được định nghĩa:**

```python
@tool
def search_legal_database(query: str) -> str:
    """Tra cứu knowledge base pháp lý (UCC, DTSA, GDPR, SOX...)"""

@tool
def calculate_damages(breach_type: str, contract_value: float) -> str:
    """Tính ước tính thiệt hại theo loại vi phạm và giá trị hợp đồng"""

@tool
def check_statute_of_limitations(case_type: str) -> str:
    """Tra thời hiệu khởi kiện: contract=4 năm, tort=2-3 năm, property=5 năm"""
```

**Luồng xử lý:**
1. Bind tools vào LLM: `llm.bind_tools(TOOLS)`
2. LLM quyết định tool nào cần gọi
3. Thực thi tool, gắn `ToolMessage` vào messages
4. LLM tổng hợp câu trả lời cuối

**Cải thiện so với Stage 1:** Grounded — trích dẫn điều luật cụ thể, giảm hallucination.

---

## Stage 3 — Single Agent (ReAct Loop)

**File:** `stages/stage_3_single_agent/main.py`

Dùng `create_react_agent` để agent tự động lặp Think → Act → Observe.

```python
from langgraph.prebuilt import create_react_agent

graph = create_react_agent(model=llm, tools=TOOLS, prompt=SYSTEM_PROMPT)

async for chunk in graph.astream(inputs, stream_mode="updates"):
    # agent tự quyết định gọi tool nào, bao nhiêu lần
```

**Tools mở rộng thêm:**
- `calculate_penalty(violation_type, severity, annual_revenue)` — ước tính mức phạt
- `check_compliance_requirements(industry, company_size)` — khung pháp lý áp dụng
- `search_case_law(keywords)` — tra án lệ (Hadley v. Baxendale, Donoghue v. Stevenson...)

**Cải thiện:** Agent tự chủ, multi-step reasoning, gọi nhiều tools theo thứ tự hợp lý.

---

## Stage 4 — Multi-Agent System (In-Process)

**File:** `stages/stage_4_milti_agent/main.py`

Nhiều agent chuyên biệt chạy song song trong cùng một process, dùng LangGraph `Send` API.

**Kiến trúc graph:**
```
analyze_law → check_routing → ┬→ call_tax_specialist    ┐
                               ├→ call_compliance_spec.  ├→ aggregate → END
                               └→ call_privacy_spec.     ┘
```

**State:**
```python
class LegalState(TypedDict):
    question: str
    law_analysis: str
    needs_tax: bool
    needs_compliance: bool
    needs_privacy: bool
    tax_result: Annotated[str, _last_wins]      # parallel write safe
    compliance_result: Annotated[str, _last_wins]
    privacy_result: Annotated[str, _last_wins]
    final_answer: str
```

**Routing dựa trên keyword:**
```python
def check_routing(state: LegalState) -> list[Send]:
    tasks = []
    if any(kw in question for kw in ["tax", "irs", "thuế"]):
        tasks.append(Send("call_tax_specialist", state))
    if any(kw in question for kw in ["compliance", "sec", "regulation"]):
        tasks.append(Send("call_compliance_specialist", state))
    if any(kw in question for kw in ["data", "privacy", "gdpr", "dữ liệu"]):
        tasks.append(Send("call_privacy_specialist", state))
    return tasks or [Send("aggregate", state)]
```

**Lỗi đã sửa trong session:**

| Lỗi | Fix |
|-----|-----|
| `privacy_agent` dùng `State` (undefined), là hàm orphan | Xóa hàm |
| `check_routing` dùng `State`, là `async`, gọi sai tên nodes (`tax_agent`, `aggregate_results`) | Sửa type hint, bỏ `async`, sửa tên |
| `route_to_specialists` đọc `needs_*` fields nhưng chúng không bao giờ được set | Xóa, gộp vào `check_routing` |
| Graph add `check_routing` làm node + dùng `route_to_specialists` làm conditional edge | Dùng `check_routing` trực tiếp làm conditional edge sau `analyze_law` |
| `IPython.display` nằm ngoài scope, `graph` undefined | Xóa |

---

## Stage 5 — Distributed A2A Multi-Agent System

**Kiến trúc dịch vụ:**

| Service | Port | Vai trò |
|---------|------|---------|
| Registry | 10000 | Đăng ký & discovery agents |
| Customer Agent | 10100 | Entry point, nhận câu hỏi từ user |
| Law Agent | 10101 | Orchestrator, điều phối Tax + Compliance |
| Tax Agent | 10102 | Chuyên gia thuế (ReAct agent) |
| Compliance Agent | 10103 | Chuyên gia compliance (ReAct agent) |

**Khởi động:**
```bash
./start_all.sh        # khởi động tất cả services
python test_client.py # gửi câu hỏi test
```

**Luồng request:**
```
test_client → Customer Agent → Law Agent → (Tax Agent & Compliance Agent) → aggregate → response
```

**A2A Protocol — gửi request giữa agents:**
```python
# common/a2a_client.py
from a2a.client import ClientFactory, ClientConfig

config = ClientConfig(httpx_client=http_client, streaming=False)
client = ClientFactory(config).create(agent_card)

final_result = None
async for event in client.send_message(message):   # async generator
    if isinstance(event, tuple):
        final_result = event[0]   # Task
    else:
        final_result = event      # Message
```

**AgentExecutor bridge (Law Agent):**
```python
class LawAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        result = await _graph.ainvoke(initial_state)
        await updater.add_artifact(parts=[Part(root=TextPart(text=answer))])
        await updater.complete()
```

**Lỗi đã fix trong session:**

| Lỗi | Fix |
|-----|-----|
| Package `a2a` v0.44 (Azure tool) chiếm namespace, block `a2a-sdk` | Gỡ `a2a`, cài `a2a-sdk[http-server]>=0.3.0` |
| `A2AClient` deprecated | Chuyển sang `ClientFactory` + `ClientConfig` |
| `await client.send_message()` — API mới trả async generator | Đổi thành `async for event in client.send_message(message)` |
| `send_message(MessageSendParams)` — API mới nhận `Message` trực tiếp | Bỏ wrap, truyền `Message` thẳng |
| `get_llm()` không có timeout, treo 300s khi API chậm | Thêm `request_timeout=60` |
| `base_url` hardcode trong `get_llm()` | Đọc từ env var `base_url` |

---

## Exercise 2 — Tools và Knowledge Base

**File:** `exercises/exercise_2_tools.py`  
**Mục tiêu:** Học cách định nghĩa tools và gắn vào LLM.

**Đã làm:**

1. Thêm entry `labor_law` vào `LEGAL_KNOWLEDGE`:
```python
{
    "id": "labor_law",
    "keywords": ["lao động", "sa thải", "hợp đồng lao động", "labor", "termination"],
    "text": "Theo Bộ luật Lao động Việt Nam 2019...",
}
```

2. Tạo tool `check_statute_of_limitations`:
```python
@tool
def check_statute_of_limitations(case_type: str) -> str:
    """Kiểm tra thời hiệu khởi kiện theo loại vụ án."""
    limits = {
        "contract": "4 năm (UCC § 2-725)",
        "tort": "2-3 năm tùy bang",
        "property": "5 năm",
    }
    return limits.get(case_type.lower(), "Không xác định")
```

3. Vòng lặp tool call thủ công:
```python
llm_with_tools = llm.bind_tools(tools)
response = await llm_with_tools.ainvoke(messages)

if response.tool_calls:
    for tool_call in response.tool_calls:
        tool_result = search_legal_knowledge.invoke(tool_call["args"])
        messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call["id"]))
    
    final_response = await llm_with_tools.ainvoke(messages)
```

**Câu hỏi test:** *"Thời hiệu khởi kiện vụ vi phạm hợp đồng là bao lâu?"*

---

## Exercise 4 — Multi-Agent với Privacy Agent

**File:** `exercises/exercise_4_multiagent.py`  
**Mục tiêu:** Mở rộng multi-agent system với agent chuyên biệt mới.

**Đã làm:**

1. Định nghĩa `privacy_agent`:
```python
def privacy_agent(state: State) -> dict:
    """Agent chuyên về bảo vệ dữ liệu cá nhân và GDPR."""
    llm = get_llm()
    prompt = f"""Bạn là chuyên gia về GDPR và luật bảo vệ dữ liệu cá nhân.
    Câu hỏi gốc: {state['question']}
    Tập trung: GDPR, CCPA, data breach notification, mức phạt."""
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"privacy_analysis": response.content}
```

2. Thêm routing condition cho privacy:
```python
def check_routing(state: State) -> list[Send]:
    tasks = []
    if any(kw in question for kw in ["data", "privacy", "gdpr", "dữ liệu", "ccpa", "rò rỉ"]):
        tasks.append(Send("privacy_agent", state))
    ...
```

3. Thêm `privacy_analysis` field vào State và tích hợp vào `aggregate_results`.

4. Thêm node vào graph:
```python
graph.add_node("privacy_agent", privacy_agent)
graph.add_edge("privacy_agent", "aggregate_results")
```

**Câu hỏi test:** *"Nếu công ty bị rò rỉ dữ liệu khách hàng, hậu quả pháp lý và thuế là gì?"*

---

## So Sánh Các Stages

| | Stage 1 | Stage 2 | Stage 3 | Stage 4 | Stage 5 |
|---|---------|---------|---------|---------|---------|
| Kiến trúc | Direct LLM | LLM + Tools | ReAct Agent | In-process Multi-Agent | Distributed A2A |
| Tools | Không | Thủ công | Tự động | Chuyên biệt theo agent | Chuyên biệt + A2A protocol |
| Song song | Không | Không | Không | Có (Send API) | Có (HTTP + Send API) |
| Grounding | Không | Có | Có | Có | Có |
| Deployment | 1 process | 1 process | 1 process | 1 process | 5 services độc lập |
| Scale | Không | Không | Không | Hạn chế | Độc lập theo service |

---

## Key Concepts

### LangGraph Send API (Parallel Dispatch)
```python
from langgraph.constants import Send

def router(state) -> list[Send]:
    return [
        Send("agent_a", state),   # chạy song song
        Send("agent_b", state),   # chạy song song
    ]

graph.add_conditional_edges("router_node", router, ["agent_a", "agent_b"])
```

### Annotated Reducer (tránh xung đột khi ghi song song)
```python
from typing import Annotated

def _last_wins(a: str, b: str) -> str:
    return b if b else a

class State(TypedDict):
    result: Annotated[str, _last_wins]  # an toàn cho parallel write
```

### A2A Agent Registration
```python
await register({
    "agent_name": "tax-agent",
    "tasks": ["tax_question"],      # task ID để discover
    "endpoint": "http://localhost:10102",
})

endpoint = await discover("tax_question")   # client tìm agent qua registry
```

### AgentExecutor Pattern (A2A SDK)
```python
class MyAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.submit()
        await updater.start_work()
        # ... xử lý ...
        await updater.add_artifact(parts=[...])
        await updater.complete()
```
