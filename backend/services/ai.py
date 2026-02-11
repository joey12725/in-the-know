from __future__ import annotations

from typing import Any

import httpx

from core.config import get_settings


class OpenRouterClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def chat(self, prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
        if not self.settings.openrouter_api_key:
            return ""

        payload: dict[str, Any] = {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{self.settings.openrouter_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()


openrouter_client = OpenRouterClient()
