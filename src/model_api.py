from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from src.config import cfg


class ModelAPIError(RuntimeError):
    """Raised when an OpenAI-compatible model API call fails."""


@dataclass
class ModelAPIClient:
    base_url: str
    api_key: str
    timeout: float

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.base_url:
            raise ValueError("MODEL_API_BASE_URL must be set.")
        if not self.api_key:
            raise ValueError("MODEL_API_KEY must be set.")

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        top_p: float = 0.9,
        max_tokens: int = 512,
        stop: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not model:
            raise ValueError("model must be set for chat completion.")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = stop

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(
                self.chat_completions_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise ModelAPIError(f"Model API request failed: {e}") from e

        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise ModelAPIError(
                f"Model API HTTP {resp.status_code} from {self.chat_completions_url}: {detail}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise ModelAPIError(f"Model API returned non-JSON response: {resp.text[:500]}") from e

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelAPIError(f"Model API response missing non-empty choices: {data}")

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if content is None or content == "":
            raise ModelAPIError(f"Model API response missing message content: {data}")

        return data

    def complete_text(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        top_p: float = 0.9,
        max_tokens: int = 512,
        stop: Optional[List[str]] = None,
    ) -> str:
        data = self.create_chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop,
        )
        return data["choices"][0]["message"]["content"]


def load_model_api_client() -> ModelAPIClient:
    return ModelAPIClient(
        base_url=cfg.MODEL_API_BASE_URL,
        api_key=cfg.MODEL_API_KEY,
        timeout=cfg.MODEL_API_TIMEOUT,
    )
