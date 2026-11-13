"""OpenRouter client plus helpers for pulling JSON out of model responses.

Three model roles are configured separately so each can be swapped independently:

- `chat`:   structured extraction (hobby tags, reply classification, venue lists)
- `search`: web-grounded event research (Perplexity Sonar by default)
- `write`:  newsletter copy

With no `OPENROUTER_API_KEY` every call returns an empty string, and callers fall back
to deterministic heuristics. That keeps local development and tests fully offline.
"""

import json
import re
from typing import Any

import httpx

from itk.config import get_settings

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


class LLMClient:
    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str,
        model: str,
        temperature: float = 0.3,
        timeout: float = 30,
    ) -> str:
        settings = get_settings()
        if not settings.openrouter_api_key:
            return ""

        response = httpx.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": model,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        content: str = response.json()["choices"][0]["message"]["content"]
        return content.strip()

    def chat(self, prompt: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
        return self.complete(prompt, system_prompt=system_prompt, model=get_settings().openrouter_model)

    def search(self, prompt: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
        return self.complete(
            prompt, system_prompt=system_prompt, model=get_settings().openrouter_search_model, timeout=55
        )

    def write(self, prompt: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT, temperature: float = 0.7) -> str:
        return self.complete(
            prompt,
            system_prompt=system_prompt,
            model=get_settings().openrouter_writing_model,
            temperature=temperature,
            timeout=55,
        )


llm = LLMClient()

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _candidates(text: str, opener: str, closer: str) -> list[str]:
    text = text.strip()
    found = [text]
    found.extend(match.group(1) for match in _FENCE.finditer(text))
    start, end = text.find(opener), text.rfind(closer)
    if 0 <= start < end:
        found.append(text[start : end + 1])
    return found


def parse_json_array(text: str) -> list[Any]:
    """Best-effort parse of a JSON array from a model reply (bare, fenced, or embedded in prose)."""
    for candidate in _candidates(text or "", "[", "]"):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return parsed
    return []


def parse_json_object(text: str) -> dict[str, Any]:
    """Best-effort parse of a JSON object from a model reply."""
    for candidate in _candidates(text or "", "{", "}"):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}
