import os
import sys
import requests
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime
from openai import OpenAI, APIError

# 从环境变量获取配置
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3")
MODEL = os.environ.get("MODEL", "Kimi-K2.6")

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


def analyze_code(logs, diff):
    """调用大模型分析代码更新"""
    if not LLM_API_KEY:
        print("错误: 未设置 LLM_API_KEY 环境变量")
        return None

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
    """

    try:
        client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except APIError as e:
        print(f"❌ 大模型 API 错误: {e}")
        return None
    except Exception as e:
        print(f"❌ 调用大模型时发生错误: {e}")
        return None


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


def save_markdown_report(report, has_update=True):
    """将报告保存为 Markdown 文件到 reports/<project_name>/YYYY-MM-DD.md"""
    if not SAVE_REPORT:
        print("ℹ️ 报告保存功能已禁用")
        return None

    try:
        # 构建目录路径: reports/<project_name>
        project_report_dir = os.path.join(REPORTS_DIR, PROJECT_NAME.lower().replace(" ", "-"))
        os.makedirs(project_report_dir, exist_ok=True)

        # 文件名: YYYY-MM-DD.md
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{today}.md"
        filepath = os.path.join(project_report_dir, filename)

        # 构建 Markdown 内容
        status_text = "代码更新分析" if has_update else "同步状态通知"
        content = f"""# {PROJECT_NAME} {status_text} - {today}

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

{report}

---

*本报告由 SyncOpenCodeReview 自动生成*
"""

        # 写入文件
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"✅ 报告已保存到: {filepath}")
        return filepath
    except Exception as e:
        print(f"⚠️ 保存 Markdown 报告失败: {e}")
        return None


def main():
    print("=" * 50)
    print(f"{PROJECT_NAME} 代码更新分析工具")
    print("=" * 50)
    print(f"📊 代码更新状态: {'有更新' if HAS_UPDATE else '无更新'}")

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

    # 调用大模型分析
    print("\n🤖 开始调用大模型分析...")
    report = analyze_code(logs, diff)

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
