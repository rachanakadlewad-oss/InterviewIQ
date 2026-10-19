"""Provider-agnostic LLM client (plain HTTP via `requests`, no vendor SDK required).

DemoLLM is a marker object: when the active LLM is a DemoLLM the agents run their deterministic
rule-based demo implementations (app/agents/demo_logic.py) instead of calling a model."""
import logging

import requests

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Transport / provider failure (timeout, HTTP error, empty response)."""


class BaseLLM:
    name = "base"
    is_demo = False

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class DemoLLM(BaseLLM):
    name = "demo"
    is_demo = True

    def complete(self, system, user):
        raise LLMError("DemoLLM does not call a model")


class OpenAICompatLLM(BaseLLM):
    """Any OpenAI-compatible /chat/completions API (OpenAI, Groq, OpenRouter, Ollama, vLLM...)."""
    name = "openai"

    def __init__(self, api_key, model, base_url="", timeout=60):
        if not model:
            raise ValueError("LLM_MODEL must be set for the openai provider")
        self.api_key, self.model, self.timeout = api_key, model, timeout
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def complete(self, system, user):
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
        except Exception as e:  # network, HTTP, parsing
            raise LLMError(f"openai-compatible call failed: {e}") from e
        if not text or not text.strip():
            raise LLMError("empty LLM response")
        return text


class AnthropicLLM(BaseLLM):
    name = "anthropic"

    def __init__(self, api_key, model, timeout=60):
        if not model:
            raise ValueError("LLM_MODEL must be set for the anthropic provider")
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def complete(self, system, user):
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": self.model, "max_tokens": 2000, "temperature": 0.2, "system": system,
                      "messages": [{"role": "user", "content": user}]},
                timeout=self.timeout,
            )
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
        except Exception as e:
            raise LLMError(f"anthropic call failed: {e}") from e
        if not text.strip():
            raise LLMError("empty LLM response")
        return text


def get_llm(settings) -> BaseLLM:
    p = settings.llm_provider
    if p == "demo":
        return DemoLLM()
    if p == "openai":
        return OpenAICompatLLM(settings.llm_api_key, settings.llm_model, settings.llm_base_url, settings.llm_timeout)
    if p == "anthropic":
        return AnthropicLLM(settings.llm_api_key, settings.llm_model, settings.llm_timeout)
    raise ValueError(f"unknown provider {p}")
