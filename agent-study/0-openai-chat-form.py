import requests

url = "http://10.8.0.142:1234/v1/chat/completions"

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
    data = response.json()
    print(data)
else:
    print(f"Request failed with status code: {response.status_code}")
    print(response.text)