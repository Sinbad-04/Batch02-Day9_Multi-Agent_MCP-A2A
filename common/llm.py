"""Shared LLM factory for all agents.

Uses OpenRouter as an OpenAI-compatible API, so any provider's model
can be selected via the OPENROUTER_MODEL env var.
"""

import os

from langchain_openai import ChatOpenAI


def get_llm() -> ChatOpenAI:
    """Return a ChatOpenAI client pointed at the configured API endpoint."""
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "anthropic/claude-sonnet-4-5"),
        openai_api_key=os.getenv("ckey_api"),
        openai_api_base=os.getenv("base_url", "https://api.xah.io/v1"),
        temperature=0.3,
        request_timeout=60,
    )