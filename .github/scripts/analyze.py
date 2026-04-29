import os
import sys
import requests
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime
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
    print("⚠️ 警告: google-genai 库未安装，Gemini 模型将不可用")
    print("   安装命令: pip install google-genai")

# ==================== 配置管理 ====================

class ModelConfig:
    """模型配置类"""
    def __init__(self):
        # 火山引擎配置 (OpenAI 兼容接口)
        self.volc_api_key = os.getenv("LLM_API_KEY")
        self.volc_base_url = os.getenv("LLM_BASE_URL") or "https://ark.cn-beijing.volces.com/api/coding/v3"
        self.volc_model = os.getenv("MODEL") or "Kimi-K2.6"
        
        # Gemini 配置
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL") or "gemini-flash-latest"
        
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


# ==================== 模型接口抽象 ====================

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


class VolcEngineClient(BaseModelClient):
    """火山引擎模型客户端 (OpenAI 兼容)"""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
        before_sleep=lambda retry_state: print(f"🔄 火山引擎请求失败，正在重试（第 {retry_state.attempt_number}/3 次）...")
    )
    def generate(self, prompt: str, temperature: float = 0.3, timeout: int = 60, **kwargs) -> Optional[str]:
        """调用火山引擎模型"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                timeout=timeout
            )
            return response.choices[0].message.content
        except APIConnectionError as e:
            print(f"❌ 火山引擎 API 连接错误: {e}")
            print(f"   请求地址: {self.base_url}")
            print(f"   可能原因: 网络不通、IP被封禁、地址配置错误")
            raise
        except APITimeoutError as e:
            print(f"❌ 火山引擎 API 请求超时: {e}")
            raise
        except AuthenticationError as e:
            print(f"❌ 火山引擎 API 认证失败: {e}")
            print(f"   请检查 LLM_API_KEY 是否正确")
            return None
        except APIError as e:
            print(f"❌ 火山引擎 API 返回错误: {e}")
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
            print(f"❌ 调用火山引擎时发生未知错误: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_model_info(self) -> Dict[str, str]:
        return {
            "provider": "火山引擎",
            "model": self.model,
            "base_url": self.base_url
        }


class GeminiClient(BaseModelClient):
    """Gemini 模型客户端"""
    
    def __init__(self, api_key: str, model: str):
        if not GENAI_AVAILABLE:
            raise ImportError("google-genai 库未安装，无法使用 Gemini 模型")
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
                },
                request_options={"timeout": timeout}
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


# ==================== 模型工厂 ====================

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


# ==================== 其他配置 ====================

# Webhook 配置
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
DINGTALK_WEBHOOK_URL = os.getenv("DINGTALK_WEBHOOK_URL")
DINGTALK_SECRET = os.getenv("DINGTALK_SECRET")  # 钉钉加签密钥
WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL")

# 是否有代码更新
HAS_UPDATE = os.getenv("HAS_UPDATE", "true").lower() == "true"

# 仓库目录名称
REPO_DIR = os.getenv("REPO_DIR", "weknora-fork")

# 项目名称
PROJECT_NAME = os.getenv("PROJECT_NAME", "WeKnora")

# 报告保存配置
SAVE_REPORT = os.getenv("SAVE_REPORT", "true").lower() == "true"
REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")


# ==================== 工具函数 ====================

def read_file(filepath):
    """读取文件内容，增强错误处理"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"错误: 文件 {filepath} 不存在")
        return None
    except Exception as e:
        print(f"错误: 读取文件 {filepath} 失败 - {e}")
        return None


def build_dingtalk_sign(secret):
    """生成钉钉加签"""
    timestamp = str(round(time.time() * 1000))
    secret_enc = secret.encode('utf-8')
    string_to_sign = f"{timestamp}\n{secret}"
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign


def build_webhook_payload(report, webhook_type, has_update=True):
    """根据平台类型构建对应的 webhook payload"""
    title = f"{PROJECT_NAME} 代码更新分析" if has_update else f"{PROJECT_NAME} 同步状态通知"
    
    if webhook_type == "feishu":
        return {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [[{"tag": "text", "text": report}]]
                    }
                }
            }
        }
    elif webhook_type == "dingtalk":
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"## {title}\n\n{report}"
            }
        }
    elif webhook_type == "wecom":
        return {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n\n{report}"
            }
        }
    else:
        return {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [[{"tag": "text", "text": report}]]
                    }
                }
            }
        }


def send_webhook(url, payload, platform_name, secret=None):
    """发送 webhook 通知，统一处理错误"""
    if not url:
        print(f"ℹ️ {platform_name} Webhook URL 未配置，跳过")
        return True

    try:
        # 钉钉需要加签
        if platform_name == "钉钉" and secret:
            timestamp, sign = build_dingtalk_sign(secret)
            url = f"{url}&timestamp={timestamp}&sign={sign}"
            print(f"🔐 {platform_name} 已添加加签参数")

        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()

        # 检查钉钉返回的业务状态码
        if platform_name == "钉钉":
            result = resp.json()
            if result.get("errcode") != 0:
                print(f"⚠️ {platform_name} Webhook 推送失败: {result.get('errmsg')}")
                return False

        print(f"✅ {platform_name} Webhook 推送成功！")
        return True
    except requests.exceptions.Timeout:
        print(f"⚠️ {platform_name} Webhook 推送超时")
        return False
    except requests.exceptions.RequestException as e:
        print(f"⚠️ {platform_name} Webhook 推送失败: {e}")
        return False


def analyze_code(logs, diff, model_client: BaseModelClient):
    """调用大模型分析代码更新"""
    # 截断过长 Diff，防止超出大模型上下文
    max_chars = 100000
    original_diff_len = len(diff)
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n\n...[Diff过长已截断]..."
        print(f"⚠️ Diff 长度 ({original_diff_len}) 超过限制，已截断至 {max_chars} 字符")

    prompt = f"""
    你是一个资深的架构师和代码审查专家。以下是 {PROJECT_NAME} 仓库最新的代码提交记录和代码差异。

    【新增提交记录】
    {logs}

    【代码差异】
    {diff}

    请你根据以上信息，输出一份详细的代码迭代报告，必须包含以下三部分：

    1. **迭代功能清单**：
       - 以表格或列表形式罗列出本次更新的所有功能点
       - 每个功能点需包含：功能名称、功能描述、相关文件路径（从代码差异中提取具体的文件路径）
       - 如果是Bug修复，需说明修复的问题和涉及的文件位置

    2. **迭代功能总结**：
       - 本次更新的核心功能概述
       - 修复的Bug汇总
       - 整体影响范围评估

    3. **优劣与风险分析**：
       - **优势/亮点**：代码实现上有哪些优秀的实践（如性能提升、架构优化等）
       - **劣势/风险**：指出代码中潜在的问题、技术债务、安全隐患或可以优化的地方

    注意：
    - 功能清单中的文件路径必须准确，从代码差异的 `+++ b/` 或 `--- a/` 行中提取
    - 如果涉及多个文件的修改，请逐一列出
    - 对于新增功能，标注 `[新增]`；对于修复，标注 `[修复]`；对于优化，标注 `[优化]`
    - 如果涉及多个功能模块，请在每个完整的模块内容前添加分隔标记：`---模块分隔：[模块名称]---`
      （模块名称请使用简洁的中文名称，最多8个字符，不要包含特殊字符）
    """
    
    # 使用模型客户端生成内容
    return model_client.generate(prompt, temperature=0.3, timeout=60)


def write_github_summary(report):
    """将报告写入 GitHub Actions Summary"""
    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary_file:
        try:
            with open(step_summary_file, "a", encoding="utf-8") as f:
                f.write(f"## 🤖 {PROJECT_NAME} 每日代码更新与分析报告\n\n")
                f.write(report)
            print("✅ 报告已写入 GitHub Step Summary")
        except Exception as e:
            print(f"⚠️ 写入 GitHub Step Summary 失败: {e}")




def split_report_by_module(full_report):
    """按模块分隔标记拆分报告为多个模块报告"""
    modules = {}
    module_separator = "---模块分隔："
    
    if module_separator not in full_report:
        # 没有模块分隔，返回空，只保存汇总报告
        return modules
    
    # 拆分模块
    parts = full_report.split(module_separator)
    # 第一部分是报告头部（迭代功能总结、优劣分析等）
    header = parts[0].strip()
    
    for part in parts[1:]:
        if "---" in part:
            module_name_end = part.find("---")
            module_name = part[:module_name_end].strip()
            # 清理模块名称特殊字符
            module_name = ''.join(c for c in module_name if c.isalnum() or c in ('_', '-', ' '))
            module_name = module_name[:15]  # 模块名称最多15个字符
            module_content = part[module_name_end + 3:].strip()
            
            # 每个模块报告包含头部信息+模块内容
            module_full_content = f"{header}\n\n## {module_name}\n\n{module_content}"
            modules[module_name] = module_full_content
    
    return modules

def save_markdown_report(report, has_update=True):
    """将报告保存为 Markdown 文件到 reports/<project_name>/
    有更新时：
    - 保存一份完整的汇总报告：YYYY-MM-DD-汇总.md
    - 如果有模块分隔标记，额外按模块保存多份报告：YYYY-MM-DD-模块名称.md
    无更新时：
    - 保存无更新报告：YYYY-MM-DD-无更新.md
    """
    if not SAVE_REPORT:
        print("ℹ️ 报告保存功能已禁用")
        return None

    try:
        # 构建目录路径: reports/<project_name>
        project_report_dir = os.path.join(REPORTS_DIR, PROJECT_NAME.lower().replace(" ", "-"))
        os.makedirs(project_report_dir, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        current_exec_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 批次分隔符，区分不同执行时间的报告
        batch_separator = f"\n\n{'='*80}\n===== 执行批次：{current_exec_time} =====\n{'='*80}\n\n"
        saved_files = []

        # 无更新时直接保存无更新报告
        if not has_update:
            filename = f"{today}-无更新.md"
            filepath = os.path.join(project_report_dir, filename)
            status_text = "同步状态通知"
            content = batch_separator + f"""# {PROJECT_NAME} {status_text} - {today}

> 生成时间: {current_exec_time}

---

{report}

---

*本报告由 SyncOpenCodeReview 自动生成*
"""
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ 无更新报告已保存到: {filepath}")
            saved_files.append(filepath)
            return saved_files

        # 有更新时，先保存汇总报告
        summary_filename = f"{today}-汇总.md"
        summary_filepath = os.path.join(project_report_dir, summary_filename)
        status_text = "代码更新分析"
        summary_content = batch_separator + f"""# {PROJECT_NAME} {status_text} - {today}

> 生成时间: {current_exec_time}

---

{report}

---

*本报告由 SyncOpenCodeReview 自动生成*
"""
        with open(summary_filepath, "a", encoding="utf-8") as f:
            f.write(summary_content)
        print(f"✅ 汇总报告已保存到: {summary_filepath}")
        saved_files.append(summary_filepath)

        # 尝试拆分模块报告
        modules = split_report_by_module(report)
        if modules:
            print(f"🔍 检测到 {len(modules)} 个功能模块，正在生成模块报告...")
            for module_name, module_content in modules.items():
                # 清理模块名称中的空格，替换为短横线
                clean_module_name = module_name.replace(" ", "-")
                module_filename = f"{today}-{clean_module_name}.md"
                module_filepath = os.path.join(project_report_dir, module_filename)
                module_full_content = batch_separator + f"""# {PROJECT_NAME} {module_name} 模块更新分析 - {today}

> 生成时间: {current_exec_time}
> 所属版本: {today}

---

{module_content}

---

*本报告由 SyncOpenCodeReview 自动生成*
"""
                with open(module_filepath, "a", encoding="utf-8") as f:
                    f.write(module_full_content)
                print(f"✅ 模块报告已保存到: {module_filepath}")
                saved_files.append(module_filepath)

        return saved_files
    except Exception as e:
        print(f"⚠️ 保存 Markdown 报告失败: {e}")
        return None


def main():
    print("=" * 50)
    print(f"{PROJECT_NAME} 代码更新分析工具")
    print("=" * 50)
    print(f"📊 代码更新状态: {'有更新' if HAS_UPDATE else '无更新'}")
    
    # 初始化配置
    config = ModelConfig()
    
    # 检查模型配置
    active_provider = config.get_active_provider()
    if not active_provider:
        print("❌ 错误: 未配置任何有效的模型")
        print("   请设置 GEMINI_API_KEY 或 LLM_API_KEY 环境变量")
        return 1
    
    print(f"🔧 模型提供商: {active_provider}")
    
    # 如果没有更新，直接发送无更新通知
    if not HAS_UPDATE:
        report = "✅ 今日上游仓库没有新的代码更新，跳过分析与同步。"
        print("ℹ️ 没有代码更新，发送无更新通知...")

        # 输出到 GitHub Actions Summary
        write_github_summary(report)

        # 保存 Markdown 报告
        print("\n💾 保存 Markdown 报告...")
        save_markdown_report(report, has_update=False)

        # 发送 Webhook 通知
        print("\n📤 发送 Webhook 通知...")
        webhook_configs = [
            (FEISHU_WEBHOOK_URL, "feishu", "飞书", None),
            (DINGTALK_WEBHOOK_URL, "dingtalk", "钉钉", DINGTALK_SECRET),
            (WECOM_WEBHOOK_URL, "wecom", "企微", None),
        ]

        success_count = 0
        for url, webhook_type, name, secret in webhook_configs:
            if url:
                payload = build_webhook_payload(report, webhook_type, has_update=False)
                if send_webhook(url, payload, name, secret):
                    success_count += 1

        print(f"\n📊 通知发送完成: {success_count}/3 成功")
        print("=" * 50)
        return 0

    # 读取日志和 diff 文件（支持从 REPO_DIR 子目录读取）
    logs = read_file(f"{REPO_DIR}/.github/new_logs.txt")
    if logs is None:
        logs = read_file(".github/new_logs.txt")
    diff = read_file(f"{REPO_DIR}/.github/new_diff.txt")
    if diff is None:
        diff = read_file(".github/new_diff.txt")

    if logs is None or diff is None:
        print("❌ 读取输入文件失败，退出分析")
        return 1

    if not logs.strip():
        print("ℹ️ 没有更新记录，退出分析")
        return 0

    print(f"📄 读取到 {len(logs)} 字符的提交记录")
    print(f"📄 读取到 {len(diff)} 字符的代码差异")
    
    # 创建模型客户端
    model_client = ModelFactory.create_client(config)
    if not model_client:
        return 1
    
    model_info = model_client.get_model_info()
    print(f"   提供商: {model_info['provider']}")
    print(f"   模型: {model_info['model']}")
    
    # 调用大模型分析
    print("\n🤖 开始调用大模型分析...")
    report = analyze_code(logs, diff, model_client)

    if not report:
        print("❌ 分析失败，无法生成报告")
        return 1

    print("✅ 分析完成")

    # 输出到 GitHub Actions Summary
    write_github_summary(report)

    # 保存 Markdown 报告
    print("\n💾 保存 Markdown 报告...")
    report_path = save_markdown_report(report, has_update=True)

    # 发送 Webhook 通知
    print("\n📤 发送 Webhook 通知...")

    webhook_configs = [
        (FEISHU_WEBHOOK_URL, "feishu", "飞书", None),
        (DINGTALK_WEBHOOK_URL, "dingtalk", "钉钉", DINGTALK_SECRET),
        (WECOM_WEBHOOK_URL, "wecom", "企微", None),
    ]

    success_count = 0
    for url, webhook_type, name, secret in webhook_configs:
        if url:
            payload = build_webhook_payload(report, webhook_type, has_update=True)
            if send_webhook(url, payload, name, secret):
                success_count += 1

    print(f"\n📊 通知发送完成: {success_count}/3 成功")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
