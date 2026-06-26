import json
import requests


class APIClient:
    PROVIDERS = {
        "qwen": {
            "name": "通义千问",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-long"],
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-3.5-turbo", "gpt-4", "gpt-4o", "gpt-4o-mini"],
        },
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-chat", "deepseek-coder"],
        },
        "zhipu": {
            "name": "智谱AI",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "models": ["glm-4", "glm-4-flash", "glm-3-turbo"],
        },
        "moonshot": {
            "name": "月之暗面",
            "base_url": "https://api.moonshot.cn/v1",
            "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        },
        "custom": {
            "name": "自定义API",
            "base_url": "",
            "models": [],
        },
    }

    def __init__(self, provider="qwen", api_key="", base_url="", model=""):
        self.provider = provider
        self.api_key = api_key
        info = self.PROVIDERS.get(provider, self.PROVIDERS["custom"])
        self.base_url = base_url or info["base_url"]
        self.model = model or (info["models"][0] if info["models"] else "")

    def chat(self, messages, temperature=0.7, max_tokens=1024, stream=False):
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if stream:
            return self._stream_request(url, headers, payload)
        else:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _stream_request(self, url, headers, payload):
        resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    @staticmethod
    def list_providers():
        return [{"id": k, "name": v["name"], "models": v["models"]} for k, v in APIClient.PROVIDERS.items()]
