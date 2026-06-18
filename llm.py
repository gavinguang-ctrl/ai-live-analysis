"""LLM 提供方 — 复盘推理(Opus 4.8 / Anthropic) + 视频分析(Gemini)。

复用 darwin 的 provider 模式。新增 claude-opus-4-8 映射。
"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str = "") -> str: ...


class AnthropicProvider(LLMProvider):
    # 代理侧模型名映射（fucheers 代理）
    _PROXY_MODEL_MAP = {
        "claude-opus-4-8": "claude-opus-4-8",
        "claude-opus-4-7": "claude-opus-4-7",
        "claude-sonnet-4-20250514": "claude-sonnet-4-6",
    }

    def __init__(self, api_key: str, model: str = "claude-opus-4-8"):
        from config import ANTHROPIC_PROXY_URL
        import httpx, anthropic
        self._is_proxy = bool(ANTHROPIC_PROXY_URL)
        if self._is_proxy:
            http_client = httpx.Client(timeout=600, proxy=None)
            self.client = anthropic.Anthropic(api_key=api_key, base_url=ANTHROPIC_PROXY_URL,
                                              http_client=http_client)
        else:
            self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(self, prompt: str, system: str = "") -> str:
        import time
        model = self._PROXY_MODEL_MAP.get(self.model, self.model) if self._is_proxy else self.model
        kwargs = {"model": model, "max_tokens": 16384,
                  "messages": [{"role": "user", "content": prompt}]}
        if system:
            kwargs["system"] = system
        for attempt in range(3):
            try:
                if self._is_proxy:
                    chunks = []
                    with self.client.messages.stream(**kwargs) as stream:
                        for text in stream.text_stream:
                            chunks.append(text)
                    return "".join(chunks)
                resp = self.client.messages.create(**kwargs)
                return resp.content[0].text
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(3 + attempt * 3)


class GoogleProvider(LLMProvider):
    """文本生成用代理；视频分析见 video_analyze.py（需官方 SDK 的 Files API）。"""
    _PROXY_MODEL_MAP = {
        "gemini-3-flash-preview": "gemini-3-flash",
        "gemini-3.1-pro-preview": "gemini-3.1-pro-high",
    }

    def __init__(self, api_key: str, model: str = "gemini-3.1-pro-preview", use_proxy: bool = True):
        from config import GOOGLE_PROXY_KEY, GOOGLE_PROXY_URL
        self._api_key = api_key
        self._proxy_key = GOOGLE_PROXY_KEY
        self._proxy_url = GOOGLE_PROXY_URL
        self.model = model
        self._use_proxy = use_proxy

    def generate(self, prompt: str, system: str = "") -> str:
        import time, httpx
        from openai import OpenAI
        full = f"{system}\n\n{prompt}" if system else prompt
        proxy_model = self._PROXY_MODEL_MAP.get(self.model, self.model)
        for attempt in range(4):
            try:
                http_client = httpx.Client(timeout=300, proxy=None)
                client = OpenAI(api_key=self._proxy_key, base_url=f"{self._proxy_url}/v1",
                                http_client=http_client)
                chunks = []
                stream = client.chat.completions.create(
                    model=proxy_model, messages=[{"role": "user", "content": full}],
                    max_tokens=16384, stream=True)
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        chunks.append(chunk.choices[0].delta.content)
                text = "".join(chunks)
                if text:
                    return text
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(3 + attempt * 3)
        raise ValueError("Google 代理调用失败")


_GOOGLE_MODELS = ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash"]

PROVIDERS = {
    "anthropic": {"class": AnthropicProvider,
                  "models": ["claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-4-20250514"]},
    "google（代理）": {"class": GoogleProvider, "models": _GOOGLE_MODELS, "extra": {"use_proxy": True}},
    "google（官方）": {"class": GoogleProvider, "models": _GOOGLE_MODELS, "extra": {"use_proxy": False}},
}


def get_provider(provider_name: str, api_key: str, model: str = "") -> LLMProvider:
    info = PROVIDERS[provider_name]
    kwargs = {"api_key": api_key}
    if model:
        kwargs["model"] = model
    kwargs.update(info.get("extra", {}))
    return info["class"](**kwargs)


def get_reasoner() -> LLMProvider:
    """复盘推理模型（默认 Opus 4.8）。"""
    from config import get_default_models, api_key_for
    m = get_default_models()["reasoner"]
    return get_provider(m["provider"], api_key_for(m["provider"]), m["model"])
