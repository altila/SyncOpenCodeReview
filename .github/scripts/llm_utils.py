"""
LLM 调用公共工具类
提供统一的大模型调用接口，支持多种LLM类型和自动降级机制
"""
import os
from typing import List, Optional, Dict, Any
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, AuthenticationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from llm_config import LLM_CONFIGS, SUPPORTED_LLM_TYPES
from llm_clients import BaseModelClient, OpenAIClient, VolcEngineClient, GeminiClient, GENAI_AVAILABLE


def get_llm_config(llm_type):
    """
    根据LLM类型获取对应的配置
    :param llm_type: 大模型类型
    :return: 配置字典，如果类型不支持返回None
    """
    llm_type = llm_type.lower()
    if llm_type not in SUPPORTED_LLM_TYPES:
        print(f"❌ 不支持的LLM类型: {llm_type}")
        print(f"   支持的类型: {', '.join(SUPPORTED_LLM_TYPES)}")
        return None
    
    config = LLM_CONFIGS[llm_type].copy()
    
    # 优先使用环境变量中的配置
    env_prefix = f"{llm_type.upper()}_"
    config["api_key"] = os.getenv(f"{env_prefix}API_KEY") or os.getenv("LLM_API_KEY")
    config["base_url"] = os.getenv(f"{env_prefix}BASE_URL") or os.getenv("LLM_BASE_URL") or config["default_base_url"]
    config["model"] = os.getenv(f"{env_prefix}MODEL") or os.getenv("MODEL") or config["default_model"]
    
    if not config["api_key"]:
        # Ollama不需要API_KEY
        if llm_type != "ollama":
            print(f"❌ 未设置 {llm_type.upper()}_API_KEY 或 LLM_API_KEY 环境变量")
            return None
    
    return config


def get_llm_fallback_order() -> List[str]:
    """
    获取LLM降级顺序，优先使用配置的默认LLM，然后按优先级尝试其他可用LLM
    :return: 降级顺序列表
    """
    # 从环境变量获取默认LLM和自定义降级顺序
    default_llm = os.getenv("LLM_TYPE", "kimi").lower()
    custom_fallback = os.getenv("LLM_FALLBACK_ORDER", "")
    
    if custom_fallback:
        fallback_order = [llm.strip().lower() for llm in custom_fallback.split(",") if llm.strip().lower() in SUPPORTED_LLM_TYPES]
        # 去重并确保默认LLM在第一位
        fallback_order = list(dict.fromkeys([default_llm] + fallback_order))
    else:
        # 默认降级顺序：kimi -> deepseek -> qwen -> ernie -> gpt -> gemini -> ollama
        default_order = ["kimi", "deepseek", "qwen", "ernie", "gpt", "gemini", "ollama"]
        fallback_order = list(dict.fromkeys([default_llm] + default_order))
    
    # 过滤掉不支持的LLM类型
    fallback_order = [llm for llm in fallback_order if llm in SUPPORTED_LLM_TYPES]
    
    return fallback_order


def is_llm_available(llm_type: str) -> bool:
    """
    检查指定LLM类型是否可用（配置是否齐全）
    :param llm_type: 大模型类型
    :return: 是否可用
    """
    config = get_llm_config(llm_type)
    return config is not None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
    before_sleep=lambda retry_state: print(f"🔄 大模型请求失败，正在重试（第 {retry_state.attempt_number}/3 次）...")
)
def _call_llm_single(prompt: str, llm_type: str = "kimi", temperature: float = 0.3, timeout: int = 60) -> Optional[str]:
    """
    内部函数：调用单个LLM类型，包含重试逻辑
    :param prompt: 提示词
    :param llm_type: 大模型类型
    :param temperature: 温度参数
    :param timeout: 超时时间
    :return: 模型返回的内容，失败返回None
    """
    config = get_llm_config(llm_type)
    if not config:
        return None
    
    try:
        client = OpenAI(
            api_key=config["api_key"] if config["api_key"] else "dummy_key",  # Ollama不需要key
            base_url=config["base_url"]
        )
        
        response = client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            timeout=timeout
        )
        
        return response.choices[0].message.content
        
    except APIConnectionError as e:
        print(f"❌ 大模型 API 连接错误: {e}")
        print(f"   LLM类型: {llm_type}")
        print(f"   请求地址: {config['base_url']}")
        print(f"   模型: {config['model']}")
        print(f"   可能原因: 网络不通、IP被封禁、地址配置错误")
        return None
    except APITimeoutError as e:
        print(f"❌ 大模型 API 请求超时: {e}")
        print(f"   LLM类型: {llm_type}")
        print(f"   请求地址: {config['base_url']}")
        print(f"   超时时间: {timeout}s")
        return None
    except AuthenticationError as e:
        print(f"❌ 大模型 API 认证失败: {e}")
        print(f"   LLM类型: {llm_type}")
        print(f"   请检查 {llm_type.upper()}_API_KEY 或 LLM_API_KEY 是否正确")
        return None
    except APIError as e:
        print(f"❌ 大模型 API 返回错误: {e}")
        print(f"   LLM类型: {llm_type}")
        print(f"   状态码: {e.status_code if hasattr(e, 'status_code') else '未知'}")
        if hasattr(e, 'response') and e.response:
            try:
                error_detail = e.response.json()
                print(f"   错误详情: {error_detail}")
            except:
                print(f"   响应内容: {e.response.text[:200]}...")
        return None
    except Exception as e:
        print(f"❌ 调用大模型时发生未知错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


def call_llm(prompt: str, llm_type: Optional[str] = None, temperature: float = 0.3, timeout: int = 60, enable_fallback: bool = True) -> Optional[str]:
    """
    统一的大模型调用接口，支持自动降级
    :param prompt: 提示词
    :param llm_type: 大模型类型，默认使用环境变量配置的LLM_TYPE或kimi
    :param temperature: 温度参数，默认0.3
    :param timeout: 超时时间，默认60秒
    :param enable_fallback: 是否启用自动降级机制，默认True
    :return: 模型返回的内容，所有LLM都失败返回None
    """
    if llm_type is None:
        llm_type = os.getenv("LLM_TYPE", "kimi").lower()
    
    # 如果不启用降级，直接调用指定LLM
    if not enable_fallback:
        return _call_llm_single(prompt, llm_type, temperature, timeout)
    
    # 获取降级顺序
    fallback_order = get_llm_fallback_order()
    print(f"🔍 LLM降级顺序: {', '.join(fallback_order)}")
    
    # 按顺序尝试每个LLM
    for idx, current_llm in enumerate(fallback_order):
        if not is_llm_available(current_llm):
            print(f"ℹ️ LLM {current_llm} 不可用，跳过")
            continue
        
        print(f"🤖 正在尝试第 {idx+1}/{len(fallback_order)} 个LLM: {current_llm}")
        result = _call_llm_single(prompt, current_llm, temperature, timeout)
        
        if result is not None:
            print(f"✅ LLM {current_llm} 调用成功")
            return result
        
        print(f"❌ LLM {current_llm} 调用失败，尝试下一个")
    
    # 所有LLM都失败
    print("❌ 所有LLM都调用失败，无法完成分析")
    return None


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
    
    @staticmethod
    def create_client_by_type(llm_type: str) -> Optional[BaseModelClient]:
        """根据LLM类型创建客户端（兼容现有通用LLM配置）"""
        config = get_llm_config(llm_type)
        if not config:
            return None
            
        if llm_type == "gemini" and GENAI_AVAILABLE and config.get("api_key"):
            # Gemini优先使用官方SDK
            return GeminiClient(config["api_key"], config["model"])
        else:
            # 其他LLM使用OpenAI兼容客户端
            provider_name = LLM_CONFIGS[llm_type]["description"] if llm_type in LLM_CONFIGS else llm_type.upper()
            return OpenAIClient(
                api_key=config["api_key"],
                base_url=config["base_url"],
                model=config["model"],
                provider_name=provider_name
            )


