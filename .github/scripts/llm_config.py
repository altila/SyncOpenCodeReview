"""
LLM 配置文件
定义不同类型大模型的默认配置参数
"""

# 支持的大模型类型配置
LLM_CONFIGS = {
    "kimi": {
        "default_base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "default_model": "Kimi-K2.6",
        "description": "Moonshot Kimi 大模型"
    },
    "deepseek": {
        "default_base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "description": "深度求索 DeepSeek 大模型"
    },
    "gpt": {
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "description": "OpenAI GPT 系列大模型"
    },
    "ollama": {
        "default_base_url": "http://localhost:11434/v1",
        "default_model": "llama3",
        "description": "Ollama 本地大模型"
    },
    "qwen": {
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "description": "阿里云通义千问大模型"
    },
    "ernie": {
        "default_base_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions_pro",
        "default_model": "ernie-4.0",
        "description": "百度文心一言大模型"
    },
    "gemini": {
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-3-flash-preview",
        "description": "谷歌Google Gemini大模型"
    }
}

# 默认LLM类型
DEFAULT_LLM_TYPE = "gemini"
# 支持的LLM类型列表
SUPPORTED_LLM_TYPES = list(LLM_CONFIGS.keys())
