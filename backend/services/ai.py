from __future__ import annotations

from typing import Any

import httpx

from core.config import get_settings


class OpenRouterClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _call(self, prompt: str, system_prompt: str, model: str, temperature: float = 0.3, timeout: int = 60) -> str:
        if not self.settings.openrouter_api_key:
            return ""

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{self.settings.openrouter_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

    def chat(self, prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """General purpose chat using default model."""
        return self._call(prompt, system_prompt, self.settings.openrouter_model)

    def search(self, prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """Web-grounded search using Perplexity Sonar."""
        return self._call(prompt, system_prompt, self.settings.openrouter_search_model, timeout=90)

    def write(self, prompt: str, system_prompt: str = "You are a helpful assistant.", temperature: float = 0.7) -> str:
        """Creative writing using the writing model (GPT-5.2)."""
        return self._call(prompt, system_prompt, self.settings.openrouter_writing_model, temperature=temperature, timeout=90)


openrouter_client = OpenRouterClient()
