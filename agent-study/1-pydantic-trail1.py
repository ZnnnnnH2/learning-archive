import requests
from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str | None = None


class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    model: str
    choices: list[Choice]
  
url = "http://100.107.139.24:1234/v1/chat/completions"

headers = {
  "Authorization": "Bearer sk-lm-gQhVZVvU:N4TiDU8wD38PPbK99thz",
  "Content-Type": "application/json"
}

payload = {
  "model": "qwen/qwen3-4b",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "Hello, how are you?"
    }
  ],
  "temperature": 0.7,
  "stream": False,
}

response = requests.post(url, headers=headers, json=payload)

if response.status_code == 200:
    raw_data = response.json()
    data = ChatCompletionResponse.model_validate(raw_data)
    print(data)
    print(data.choices[0].message.content)
else:
    print(f"Request failed with status code: {response.status_code}")
    print(response.text)