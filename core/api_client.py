"""
API 客户端 - 支持云端API和本地模型

支持模式：
- 仅检索 (local): 不使用LLM，直接返回知识库检索结果
- Ollama: 本地大模型，通过 http://localhost:11434/v1 访问
- 通义千问 / OpenAI / DeepSeek / 智谱AI / 月之暗面: 云端API
"""
import json
import requests
from core.logger import log


class APIClient:
    PROVIDERS = {
        "local": {
            "name": "仅检索（无模型）",
            "base_url": "",
            "models": ["retrieve-only"],
            "need_key": False,
            "description": "不使用任何大模型，直接返回知识库检索到的相关片段",
        },
        "ollama": {
            "name": "Ollama 本地模型",
            "base_url": "http://localhost:11434/v1",
            "models": ["qwen3:latest", "qwen2.5:7b", "qwen2.5:14b",
                       "deepseek-r1:8b", "deepseek-r1:14b",
                       "llama3.2:latest", "gemma3:latest",
                       "mistral:latest", "phi4:latest"],
            "need_key": False,
            "description": "需要先安装 Ollama (ollama.com)，下载模型后即可离线使用",
        },
        "qwen": {
            "name": "通义千问",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-long"],
            "need_key": True,
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-3.5-turbo", "gpt-4", "gpt-4o", "gpt-4o-mini"],
            "need_key": True,
        },
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-chat", "deepseek-coder"],
            "need_key": True,
        },
        "zhipu": {
            "name": "智谱AI",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "models": ["glm-4", "glm-4-flash", "glm-3-turbo"],
            "need_key": True,
        },
        "moonshot": {
            "name": "月之暗面",
            "base_url": "https://api.moonshot.cn/v1",
            "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
            "need_key": True,
        },
        "custom": {
            "name": "自定义API",
            "base_url": "",
            "models": [],
            "need_key": True,
        },
    }

    def __init__(self, provider="local", api_key="", base_url="", model=""):
        self.provider = provider
        self.api_key = api_key
        info = self.PROVIDERS.get(provider, self.PROVIDERS["local"])
        self.base_url = base_url or info["base_url"]
        self.model = model or (info["models"][0] if info["models"] else "")
        self.is_local = provider == "local"
        log.info(f"API客户端初始化: provider={provider}, model={self.model}")

    def chat(self, messages, temperature=0.7, max_tokens=1024, stream=False):
        """调用API聊天（同步）"""
        if self.is_local:
            return ""  # 仅检索模式不生成回答

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "none",
            "Content-Type": "application/json",
        }
        # Ollama 不需要 Bearer token
        if self.provider == "ollama":
            headers = {"Content-Type": "application/json"}

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        log.info(f"API请求: {self.base_url} model={self.model} (stream={stream})")

        if stream:
            return self._stream_request(url, headers, payload)
        else:
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                log.info(f"API响应成功: {len(content)} 字符")
                return content
            except requests.exceptions.RequestException as e:
                log.error(f"API请求失败: {e}")
                raise

    def _stream_request(self, url, headers, payload):
        try:
            resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=120)
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            log.info("API流式响应完成")
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except requests.exceptions.RequestException as e:
            log.error(f"API流式请求失败: {e}")
            raise

    @staticmethod
    def list_providers():
        return [
            {"id": k, "name": v["name"], "models": v["models"], "need_key": v.get("need_key", True)}
            for k, v in APIClient.PROVIDERS.items()
        ]

    @staticmethod
    def check_ollama():
        """检查 Ollama 是否可用"""
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                return True, models
            return False, []
        except Exception:
            return False, []