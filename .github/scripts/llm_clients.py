"""
LLM 客户端实现
提供不同大模型平台的客户端实现，统一接口
"""
import os
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, AuthenticationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# 尝试导入 google-genai，如果失败则给出友好提示
try:
    import google.genai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("⚠️ 警告: google-genai 库未安装，Gemini 官方 SDK 将不可用，将使用 OpenAI 兼容接口")


class BaseModelClient(ABC):
    """模型客户端抽象基类"""
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> Optional[str]:
        """生成文本"""
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, str]:
        """获取模型信息"""
        pass


class OpenAIClient(BaseModelClient):
    """OpenAI 兼容接口客户端（支持火山引擎、DeepSeek、Qwen、GPT、Ollama等）"""
    
    def __init__(self, api_key: str, base_url: str, model: str, provider_name: str = "OpenAI兼容"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.provider_name = provider_name
        self.client = OpenAI(api_key=api_key if api_key else "dummy_key", base_url=base_url)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
        before_sleep=lambda retry_state: print(f"🔄 {retry_state.fn.__self__.provider_name} 请求失败，正在重试（第 {retry_state.attempt_number}/3 次）...")
    )
    def generate(self, prompt: str, temperature: float = 0.3, timeout: int = 60, **kwargs) -> Optional[str]:
        """调用模型"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                timeout=timeout
            )
            return response.choices[0].message.content
        except APIConnectionError as e:
            print(f"❌ {self.provider_name} API 连接错误: {e}")
            print(f"   请求地址: {self.base_url}")
            print(f"   可能原因: 网络不通、IP被封禁、地址配置错误")
            raise
        except APITimeoutError as e:
            print(f"❌ {self.provider_name} API 请求超时: {e}")
            raise
        except AuthenticationError as e:
            print(f"❌ {self.provider_name} API 认证失败: {e}")
            print(f"   请检查 API_KEY 是否正确")
            return None
        except APIError as e:
            print(f"❌ {self.provider_name} API 返回错误: {e}")
            if hasattr(e, 'status_code'):
                print(f"   状态码: {e.status_code}")
            if hasattr(e, 'response') and e.response:
                try:
                    error_detail = e.response.json()
                    print(f"   错误详情: {error_detail}")
                except:
                    print(f"   响应内容: {e.response.text[:200]}...")
            return None
        except Exception as e:
            print(f"❌ 调用 {self.provider_name} 时发生未知错误: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_model_info(self) -> Dict[str, str]:
        return {
            "provider": self.provider_name,
            "model": self.model,
            "base_url": self.base_url
        }


class VolcEngineClient(OpenAIClient):
    """火山引擎模型客户端 (OpenAI 兼容)"""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        super().__init__(api_key, base_url, model, provider_name="火山引擎")


class GeminiClient(BaseModelClient):
    """Gemini 模型客户端（使用官方 SDK）"""
    
    def __init__(self, api_key: str, model: str):
        if not GENAI_AVAILABLE:
            raise ImportError("google-genai 库未安装，无法使用 Gemini 官方 SDK")
        self.api_key = api_key
        self.model = model
        self.client = genai.Client(api_key=api_key)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=lambda retry_state: print(f"🔄 Gemini 请求失败，正在重试（第 {retry_state.attempt_number}/3 次）...")
    )
    def generate(self, prompt: str, temperature: float = 0.3, max_output_tokens: int = 8192, 
                 timeout: int = 60, **kwargs) -> Optional[str]:
        """调用 Gemini 模型"""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": temperature,
                    "max_output_tokens": max_output_tokens
                }
            )
            return response.text
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Gemini API 错误: {type(e).__name__}: {e}")
            
            # 特定错误处理
            if "401" in error_msg or "AuthenticationError" in error_msg or "API key format is incorrect" in error_msg:
                print(f"   请检查 GEMINI_API_KEY 是否正确")
                return None
            elif "404" in error_msg or "NotFound" in error_msg or "is not found for API version" in error_msg:
                print(f"   请检查 GEMINI_MODEL 是否正确")
                print(f"   支持的模型: gemini-flash-latest, gemini-2.0-flash, gemini-1.5-flash 等")
                return None
            elif "429" in error_msg or "RateLimit" in error_msg:
                print(f"   请求频率超限，请稍后重试")
                raise
            else:
                raise
    
    def get_model_info(self) -> Dict[str, str]:
        return {
            "provider": "Google Gemini",
            "model": self.model,
            "base_url": "https://generativelanguage.googleapis.com"
        }
