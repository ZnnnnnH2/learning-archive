from typing import Literal

import httpx
from pydantic import BaseModel


class Message(BaseModel):
    role: Literal[
        "system",
        "developer",
        "user",
        "assistant",
    ]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: float = 0.7
    stream: bool = False


class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    model: str
    choices: list[Choice]


def chat(prompt: str) -> str:
    url = "http://100.107.139.24:1234/v1/chat/completions"

    headers = {
        "Authorization": "Bearer sk-lm-gQhVZVvU:N4TiDU8wD38PPbK99thz",
    }

    request = ChatCompletionRequest(
        model="qwen/qwen3-4b",
        messages=[
            Message(
                role="user",
                content=prompt,
            )
        ],
    )

    response = httpx.post(
        url,
        headers=headers,
        json=request.model_dump(),
        timeout=60,
        trust_env=False,  # skip system SOCKS/HTTP proxies (Clash ALL_PROXY)
    )

    response.raise_for_status()

    completion = ChatCompletionResponse.model_validate(response.json())

    return completion.choices[0].message.content or ""


print(chat("Do you love me?"))
