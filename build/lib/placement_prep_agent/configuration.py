"""Runtime configuration for the Placement Prep Agent.

Every field can be set (in priority order) from:
1. an environment variable with the upper-cased field name (e.g. ``LLM_MODEL``)
2. the ``configurable`` dict passed to the graph / LangGraph Studio
3. the default below
"""

import os
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field


class Configuration(BaseModel):
    """The configurable fields for the placement prep agent."""

    # ---- LLM -------------------------------------------------------------
    llm_provider: Literal["groq", "openai", "gemini", "openrouter", "ollama"] = Field(
        default="groq",
        title="LLM Provider",
        description=(
            "Where the model runs. groq/openai/gemini/openrouter are hosted APIs "
            "(need an API key); ollama runs a small model locally."
        ),
    )
    llm_model: str = Field(
        default="",
        title="LLM Model",
        description="Model name. Leave empty to use the provider's lightweight default.",
    )
    llm_api_key: str = Field(
        default="",
        title="LLM API Key",
        description=(
            "API key for the hosted provider. If empty, the provider-specific env var "
            "is used (GROQ_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY)."
        ),
    )
    llm_base_url: str = Field(
        default="",
        title="LLM Base URL",
        description="Override the OpenAI-compatible base URL (advanced).",
    )
    llm_temperature: float = Field(
        default=0.3,
        title="Temperature",
        description="Sampling temperature for the long-form generation steps.",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        title="Ollama Base URL",
        description="Base URL for a local Ollama server (only used when llm_provider=ollama).",
    )
    strip_thinking_tokens: bool = Field(
        default=True,
        title="Strip Thinking Tokens",
        description="Remove <think>...</think> blocks from reasoning-model output.",
    )

    # ---- Research --------------------------------------------------------
    search_api: Literal["duckduckgo", "tavily", "perplexity", "searxng", "none"] = Field(
        default="duckduckgo",
        title="Search API",
        description="Web search backend. duckduckgo needs no key; 'none' skips web research.",
    )
    max_research_loops: int = Field(
        default=2,
        title="Research Depth",
        description="How many follow-up search rounds to run after the initial queries.",
    )
    queries_per_round: int = Field(
        default=3,
        title="Queries per Round",
        description="Number of web searches in the first research round.",
    )
    fetch_full_page: bool = Field(
        default=False,
        title="Fetch Full Page",
        description="Download full page content for each search hit (slower, richer).",
    )

    # ---- Output ----------------------------------------------------------
    num_practice_questions: int = Field(
        default=15,
        title="Practice Questions",
        description="Total number of practice questions to generate.",
    )

    @classmethod
    def from_runnable_config(cls, config: RunnableConfig | None = None) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig + environment."""
        configurable = config["configurable"] if config and "configurable" in config else {}
        raw_values: dict[str, Any] = {
            name: os.environ.get(name.upper(), configurable.get(name))
            for name in cls.model_fields.keys()
        }
        values = {k: v for k, v in raw_values.items() if v not in (None, "")}
        return cls(**values)
