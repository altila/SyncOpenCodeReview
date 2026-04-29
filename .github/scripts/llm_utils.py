"""
LLM 调用公共工具类
提供统一的大模型调用接口
"""
import os
from typing import Optional, Dict, Any

from llm_config import LLM_CONFIGS
from llm_clients import BaseModelClient, VolcEngineClient, GeminiClient, GENAI_AVAILABLE


class ModelConfig:
    """模型配置类"""
    def __init__(self):
        # 火山引擎配置 (OpenAI 兼容接口)
        self.volc_api_key = os.getenv("LLM_API_KEY")
        self.volc_base_url = os.getenv("LLM_BASE_URL") or LLM_CONFIGS["kimi"]["default_base_url"]
        self.volc_model = os.getenv("MODEL") or LLM_CONFIGS["kimi"]["default_model"]

        # Gemini 配置
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL") or LLM_CONFIGS["gemini"]["default_model"]

        # 模型优先级配置
        self.preferred_provider = os.getenv("PREFERRED_PROVIDER", "auto").lower()
        # auto: 自动选择 (优先 Gemini -> 火山)
        # gemini: 强制使用 Gemini
        # volc: 强制使用火山引擎

    def get_active_provider(self) -> str:
        """获取当前激活的模型提供商"""
        if self.preferred_provider == "gemini":
            return "gemini" if self.gemini_api_key else ("volc" if self.volc_api_key else None)
        elif self.preferred_provider == "volc":
            return "volc" if self.volc_api_key else ("gemini" if self.gemini_api_key else None)
        else:  # auto
            if self.gemini_api_key and GENAI_AVAILABLE:
                return "gemini"
            elif self.volc_api_key:
                return "volc"
            return None


class ModelFactory:
    """模型工厂类"""

    @staticmethod
    def create_client(config: ModelConfig) -> Optional[BaseModelClient]:
        """根据配置创建模型客户端"""
        provider = config.get_active_provider()

        if provider == "gemini":
            print(f"🤖 使用模型: Google Gemini ({config.gemini_model})")
            return GeminiClient(config.gemini_api_key, config.gemini_model)
        elif provider == "volc":
            print(f"🤖 使用模型: 火山引擎 ({config.volc_model})")
            return VolcEngineClient(config.volc_api_key, config.volc_base_url, config.volc_model)
        else:
            print("❌ 错误: 未配置任何有效的模型 API Key")
            print("   请设置以下环境变量之一:")
            print("   - GEMINI_API_KEY: 用于 Google Gemini 模型")
            print("   - LLM_API_KEY: 用于火山引擎模型")
            return None
