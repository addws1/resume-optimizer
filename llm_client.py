"""
=============================================================================
简历优化助手 · LLM 客户端（抽象封装）
=============================================================================
提供统一的 LLM 调用接口，支持一键切换后端：
  - DeepSeek（默认）：通过 OpenAI SDK 调用 api.deepseek.com
  - Ollama：本地部署，通过 OpenAI 兼容接口
  - 通义千问 (Qwen)：阿里云 DashScope 兼容接口

所有实现遵循相同接口（generate / generate_stream），上层业务无需感知差异。
新增模型只需实现 AbstractLLMClient 的 generate 方法即可。
=============================================================================
"""

import time
from abc import ABC, abstractmethod
from typing import Optional, Generator

from openai import OpenAI

from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    OLLAMA_BASE_URL, OLLAMA_MODEL,
    QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL,
    LLM_TEMPERATURE, LLM_MAX_TOKENS,
)
from utils.logger import log_llm_call, log_error, log_warning


# ══════════════════════════════════════════════════════════════
# 抽象基类
# ══════════════════════════════════════════════════════════════

class AbstractLLMClient(ABC):
    """LLM 客户端抽象基类。所有模型实现必须继承此类。"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """返回提供商名称标识"""
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
    ) -> str:
        """
        调用 LLM 生成文本。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_tokens: 最大输出 token 数
            temperature: 采样温度

        Returns:
            LLM 生成的完整文本
        """
        ...

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
    ) -> Generator[str, None, None]:
        """
        流式生成（默认实现回退到非流式）。
        子类可覆写以实现真正的流式输出。
        """
        yield self.generate(prompt, system_prompt, max_tokens, temperature)


# ══════════════════════════════════════════════════════════════
# DeepSeek 客户端
# ══════════════════════════════════════════════════════════════

class DeepSeekClient(AbstractLLMClient):
    """DeepSeek API 客户端（通过 OpenAI SDK）"""

    def __init__(self, api_key: str = ""):
        # 优先使用调用方传入的 key（BYOK），回退到 .env 配置
        key = api_key or DEEPSEEK_API_KEY
        if not key:
            raise ValueError(
                "未找到 DEEPSEEK_API_KEY。请在 .env 文件中设置或配置系统环境变量。"
            )
        self._client = OpenAI(
            api_key=key,
            base_url=DEEPSEEK_BASE_URL,
        )

    @property
    def provider_name(self) -> str:
        return "deepseek"

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
    ) -> str:
        if not system_prompt:
            system_prompt = (
                "你是一位资深 HR 兼简历优化专家。"
                "请始终用中文回复，严格按照用户要求的格式输出。"
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        error_msg = ""

        try:
            response = self._client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            elapsed = (time.time() - t0) * 1000

            # 估算 token 数
            token_est = getattr(response.usage, "total_tokens", 0)

            log_llm_call(
                provider="deepseek",
                model=DEEPSEEK_MODEL,
                prompt_len=len(prompt),
                token_count=token_est,
                duration_ms=elapsed,
                success=True,
            )
            return content

        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            error_msg = str(e)
            log_llm_call(
                provider="deepseek",
                model=DEEPSEEK_MODEL,
                prompt_len=len(prompt),
                duration_ms=elapsed,
                success=False,
                error=error_msg,
            )
            log_error("deepseek_client", e, f"prompt 前100字: {prompt[:100]}")
            raise


# ══════════════════════════════════════════════════════════════
# Ollama 客户端（本地部署）
# ══════════════════════════════════════════════════════════════

class OllamaClient(AbstractLLMClient):
    """Ollama 本地模型客户端（通过 OpenAI 兼容接口）"""

    def __init__(self):
        self._client = OpenAI(
            api_key="ollama",  # Ollama 不校验 key，但 SDK 要求非空
            base_url=OLLAMA_BASE_URL,
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
    ) -> str:
        if not system_prompt:
            system_prompt = (
                "你是一位资深 HR 兼简历优化专家。"
                "请始终用中文回复，严格按照用户要求的格式输出。"
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        error_msg = ""

        try:
            response = self._client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            elapsed = (time.time() - t0) * 1000
            token_est = getattr(response.usage, "total_tokens", 0)

            log_llm_call(
                provider="ollama",
                model=OLLAMA_MODEL,
                prompt_len=len(prompt),
                token_count=token_est,
                duration_ms=elapsed,
                success=True,
            )
            return content

        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            error_msg = str(e)
            log_llm_call(
                provider="ollama",
                model=OLLAMA_MODEL,
                prompt_len=len(prompt),
                duration_ms=elapsed,
                success=False,
                error=error_msg,
            )
            log_error("ollama_client", e, "请确认 Ollama 服务已启动")
            raise


# ══════════════════════════════════════════════════════════════
# 通义千问 (Qwen) 客户端
# ══════════════════════════════════════════════════════════════

class QwenClient(AbstractLLMClient):
    """通义千问 API 客户端（阿里云 DashScope 兼容接口）"""

    def __init__(self, api_key: str = ""):
        # 优先使用调用方传入的 key（BYOK），回退到 .env 配置
        key = api_key or QWEN_API_KEY
        if not key:
            raise ValueError(
                "未找到 QWEN_API_KEY。请在 .env 文件中设置或配置系统环境变量。"
            )
        self._client = OpenAI(
            api_key=key,
            base_url=QWEN_BASE_URL,
        )

    @property
    def provider_name(self) -> str:
        return "qwen"

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
    ) -> str:
        if not system_prompt:
            system_prompt = (
                "你是一位资深 HR 兼简历优化专家。"
                "请始终用中文回复，严格按照用户要求的格式输出。"
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        error_msg = ""

        try:
            response = self._client.chat.completions.create(
                model=QWEN_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            elapsed = (time.time() - t0) * 1000
            token_est = getattr(response.usage, "total_tokens", 0)

            log_llm_call(
                provider="qwen",
                model=QWEN_MODEL,
                prompt_len=len(prompt),
                token_count=token_est,
                duration_ms=elapsed,
                success=True,
            )
            return content

        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            error_msg = str(e)
            log_llm_call(
                provider="qwen",
                model=QWEN_MODEL,
                prompt_len=len(prompt),
                duration_ms=elapsed,
                success=False,
                error=error_msg,
            )
            log_error("qwen_client", e, "通义千问 API 调用失败")
            raise


# ══════════════════════════════════════════════════════════════
# 工厂函数
# ══════════════════════════════════════════════════════════════

# 全局单例缓存
_llm_client: Optional[AbstractLLMClient] = None


def get_llm_client(provider: str = "", api_key: str = "") -> AbstractLLMClient:
    """
    获取 LLM 客户端实例。

    根据 LLM_PROVIDER 配置自动选择后端：
    - "deepseek" → DeepSeekClient
    - "ollama"   → OllamaClient
    - "qwen"     → QwenClient

    Args:
        provider: 可选，手动指定后端名称（覆盖配置文件）
        api_key: 可选，用户自带的 API Key（BYOK）。
                 传入时【绕过全局单例】每次新建实例——单例是进程级共享，
                 若缓存用户 key 会泄漏给其他会话。

    Returns:
        AbstractLLMClient 实例

    Raises:
        ValueError: 指定的 provider 不支持或缺少 API Key
    """
    global _llm_client

    from config import LLM_PROVIDER
    target = provider or LLM_PROVIDER

    # BYOK：不读不写单例，直接构造会话独立实例
    if api_key:
        if target == "deepseek":
            return DeepSeekClient(api_key=api_key)
        elif target == "ollama":
            return OllamaClient()
        elif target == "qwen":
            return QwenClient(api_key=api_key)
        else:
            raise ValueError(
                f"不支持的 LLM 提供商：{target}。"
                f"可用选项：deepseek / ollama / qwen。"
            )

    # 如果已缓存且 provider 不变，直接返回
    if _llm_client is not None and (not provider or provider == _llm_client.provider_name):
        return _llm_client

    if target == "deepseek":
        _llm_client = DeepSeekClient()
    elif target == "ollama":
        _llm_client = OllamaClient()
    elif target == "qwen":
        _llm_client = QwenClient()
    else:
        raise ValueError(
            f"不支持的 LLM 提供商：{target}。"
            f"可用选项：deepseek / ollama / qwen。"
            f"请在 config.py 或 .env 中设置 LLM_PROVIDER。"
        )

    return _llm_client


def reset_llm_client():
    """重置 LLM 客户端缓存（切换 provider 后使用）"""
    global _llm_client
    _llm_client = None
