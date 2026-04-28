"""
公共工具模块
包含所有脚本共享的通用函数
"""
import os
import requests
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime
from typing import Dict, Optional, Tuple


def read_file(filepath: str) -> Optional[str]:
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


def build_dingtalk_sign(secret: str) -> Tuple[str, str]:
    """生成钉钉加签"""
    timestamp = str(round(time.time() * 1000))
    secret_enc = secret.encode('utf-8')
    string_to_sign = f"{timestamp}\n{secret}"
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign


def build_webhook_payload(report: str, webhook_type: str, project_name: str, has_update: bool = True) -> Dict:
    """根据平台类型构建对应的 webhook payload"""
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


def send_webhook(url: str, payload: Dict, platform_name: str, secret: Optional[str] = None) -> bool:
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


def write_github_summary(report: str, report_title: str) -> None:
    """将报告写入 GitHub Actions Summary"""
    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary_file:
        try:
            with open(step_summary_file, "a", encoding="utf-8") as f:
                f.write(f"## {report_title}\n\n")
                f.write(report)
            print("✅ 报告已写入 GitHub Step Summary")
        except Exception as e:
            print(f"⚠️ 写入 GitHub Step Summary 失败: {e}")


def split_report_by_module(full_report: str) -> Dict[str, str]:
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


def save_markdown_report(report: str, project_name: str, has_update: bool = True, 
                         reports_dir: str = "reports") -> Optional[str]:
    """将报告保存为 Markdown 文件到 reports/<project_name>/
    有更新时：
    - 保存一份完整的汇总报告：YYYY-MM-DD-汇总.md
    - 如果有模块分隔标记，额外按模块保存多份报告：YYYY-MM-DD-模块名称.md
    无更新时：
    - 保存无更新报告：YYYY-MM-DD-无更新.md
    """
    save_report = os.getenv("SAVE_REPORT", "true").lower() == "true"
    if not save_report:
        print("ℹ️ 报告保存功能已禁用")
        return None

    try:
        # 构建目录路径: reports/<project_name>
        project_report_dir = os.path.join(reports_dir, project_name.lower().replace(" ", "-"))
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
            content = batch_separator + f"""# {project_name} {status_text} - {today}

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
        summary_content = batch_separator + f"""# {project_name} {status_text} - {today}

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
                module_full_content = batch_separator + f"""# {project_name} {module_name} 模块更新分析 - {today}

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
