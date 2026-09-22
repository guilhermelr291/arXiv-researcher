"""OpenAI chat models. Every call uses the Responses API."""

from __future__ import annotations

from langchain_openai import ChatOpenAI


def openai_chat(**kwargs: object) -> ChatOpenAI:
    """Build a chat model that posts to ``/v1/responses``."""
    kwargs.setdefault("use_responses_api", True)
    return ChatOpenAI(**kwargs)
