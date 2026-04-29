import os
import time
import hmac
import hashlib
import base64
import urllib.parse
import requests
from typing import Optional, Dict, Any, List, Tuple

# ========== 公共配置 ==========
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
DINGTALK_WEBHOOK_URL = os.getenv("DINGTALK_WEBHOOK_URL")
DINGTALK_SECRET = os.getenv("DINGTALK_SECRET")
WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL")

# ========== 公共函数 ==========

def build_dingtalk_sign(secret: str) -> Tuple[str, str]:
    """生成钉钉加签"""
    timestamp = str(round(time.time() * 1000))
    secret_enc = secret.encode('utf-8')
    string_to_sign = f"{timestamp}\n{secret}"
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign


def build_webhook_payload(report: str, webhook_type: str, title: Optional[str] = None, has_update: bool = True) -> Dict[str, Any]:
    """根据平台类型构建对应的 webhook payload，兼容两种脚本的调用场景"""
    if not title:
        project_name = os.getenv("PROJECT_NAME", "项目")
        title = f"{project_name} 代码更新分析" if has_update else f"{project_name} 同步状态通知"

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


def send_webhook(url: str, payload: Dict[str, Any], platform_name: str, secret: Optional[str] = None) -> bool:
    """发送 webhook 通知，统一处理错误"""
    if not url:
        print(f"ℹ️ {platform_name} Webhook URL 未配置，跳过")
        return True

    try:
        if platform_name == "钉钉" and secret:
            timestamp, sign = build_dingtalk_sign(secret)
            url = f"{url}&timestamp={timestamp}&sign={sign}"
            print(f"🔐 {platform_name} 已添加加签参数")

        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()

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


def get_webhook_configs() -> List[Tuple[Optional[str], str, str, Optional[str]]]:
    """获取统一的webhook配置列表，避免重复定义"""
    return [
        (FEISHU_WEBHOOK_URL, "feishu", "飞书", None),
        (DINGTALK_WEBHOOK_URL, "dingtalk", "钉钉", DINGTALK_SECRET),
        (WECOM_WEBHOOK_URL, "wecom", "企微", None),
    ]


def send_all_webhooks(report: str, title: Optional[str] = None, has_update: bool = True) -> int:
    """统一发送所有已配置平台的webhook通知，返回成功数量"""
    configs = get_webhook_configs()
    success_count = 0
    for url, webhook_type, name, secret in configs:
        if url:
            payload = build_webhook_payload(report, webhook_type, title, has_update)
            if send_webhook(url, payload, name, secret):
                success_count += 1
    return success_count
