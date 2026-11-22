"""LLM factory and response helpers.

All hosted providers are reached through their OpenAI-compatible endpoints, so a
single dependency (``langchain-openai``) covers Groq, OpenAI, Gemini and OpenRouter.
"""

import json
import os
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from placement_prep_agent.configuration import Configuration

# provider -> (base_url, lightweight default model, api-key env var)
PROVIDERS: dict[str, tuple[str | None, str, str | None]] = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.1-8b-instant", "GROQ_API_KEY"),
    "openai": (None, "gpt-4o-mini", "OPENAI_API_KEY"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.5-flash",
        "GEMINI_API_KEY",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "meta-llama/llama-3.1-8b-instruct",
        "OPENROUTER_API_KEY",
    ),
    "ollama": (None, "llama3.2", None),
}


class MissingAPIKeyError(RuntimeError):
    """Raised when a hosted provider is selected but no API key is configured."""


def get_llm(cfg: Configuration, temperature: float | None = None) -> BaseChatModel:
    """Build a chat model for the configured provider."""
    if cfg.llm_provider not in PROVIDERS:
        raise ValueError(f"Unsupported llm_provider: {cfg.llm_provider}")
    base_url, default_model, key_env = PROVIDERS[cfg.llm_provider]
    model = cfg.llm_model or default_model
    temp = cfg.llm_temperature if temperature is None else temperature

    if cfg.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(base_url=cfg.ollama_base_url, model=model, temperature=temp)

    from langchain_openai import ChatOpenAI

    api_key = cfg.llm_api_key or (os.environ.get(key_env, "") if key_env else "")
    if not api_key:
        raise MissingAPIKeyError(
            f"No API key for provider '{cfg.llm_provider}'. Set {key_env} (or LLM_API_KEY) "
            "in your .env file, or switch LLM_PROVIDER=ollama to run locally."
        )
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=cfg.llm_base_url or base_url,
        temperature=temp,
        max_retries=3,
        timeout=120,
    )


def strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def ask(cfg: Configuration, system: str, user: str, temperature: float | None = None) -> str:
    """Send one system+user turn and return the text reply."""
    llm = get_llm(cfg, temperature)
    result = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = result.content
    if isinstance(content, list):  # some providers return content blocks
        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return strip_thinking(content) if cfg.strip_thinking_tokens else content.strip()


def extract_json(text: str) -> Any | None:
    """Pull the first JSON object/array out of a model reply (tolerates ```json fences)."""
    text = strip_thinking(text)
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def ask_json(cfg: Configuration, system: str, user: str) -> Any | None:
    """Ask for a JSON reply at temperature 0 and parse it (None if unparseable)."""
    return extract_json(ask(cfg, system, user, temperature=0))
