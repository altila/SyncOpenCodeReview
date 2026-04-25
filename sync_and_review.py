import os
import subprocess
import requests

# 环境配置
SYNC_PAT = os.environ.get("SYNC_PAT")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3")
MODEL = os.environ.get("MODEL", "Kimi-K2.6") # 推荐使用 Kimi-K2.6, gpt-4o, claude-3-5-sonnet 或 deepseek-chat

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK")
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK")
WECOM_WEBHOOK = os.environ.get("WECOM_WEBHOOK")

FORK_REPO = f"https://{SYNC_PAT}@github.com/altila/WeKnora.git"
UPSTREAM_REPO = "https://github.com/Tencent/WeKnora.git"
CLONE_DIR = "WeKnora_clone"

def run_cmd(cmd, cwd=None):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running cmd: {cmd}\n{result.stderr}")
        raise Exception(f"Command failed: {cmd}\n{result.stderr}")
    return result.stdout.strip()

def sync_and_get_diff():
    if not SYNC_PAT:
        raise ValueError("SYNC_PAT 未配置，无法访问 Fork 仓库。")

    # 1. 克隆 Fork 仓库
    print("Cloning fork repo...")
    run_cmd(f"git clone {FORK_REPO} {CLONE_DIR}")
    
    # 配置 Git 用户信息
    run_cmd('git config user.name "github-actions[bot]"', cwd=CLONE_DIR)
    run_cmd('git config user.email "github-actions[bot]@users.noreply.github.com"', cwd=CLONE_DIR)

    # 2. 添加上游仓库并获取更新
    print("Adding and fetching upstream...")
    run_cmd(f"git remote add upstream {UPSTREAM_REPO}", cwd=CLONE_DIR)
    run_cmd("git fetch upstream main", cwd=CLONE_DIR)
    
    # 3. 检查是否有更新
    commits = run_cmd("git log HEAD..upstream/main --oneline", cwd=CLONE_DIR)
    if not commits:
        print("上游仓库没有新的提交，已是最新状态。")
        return None
    
    # 4. 获取代码 Diff
    diff = run_cmd("git diff HEAD..upstream/main", cwd=CLONE_DIR)
    
    # 5. 合并更新并推送到 Fork 仓库
    print("Merging and pushing to fork...")
    run_cmd("git merge upstream/main -m 'Merge upstream main'", cwd=CLONE_DIR)
    run_cmd("git push origin main", cwd=CLONE_DIR)
    
    return diff

def analyze_diff(diff):
    if not OPENAI_API_KEY:
        return "代码已同步，但未配置大语言模型 API_KEY，无法进行代码分析。"

    # 如果 Diff 过大，进行截断以防超出大模型上下文长度
    if len(diff) > 100000:
        diff = diff[:100000] + "\n...[由于长度限制，Diff被截断]"
    
    prompt = f"""
请分析以下代码的更新（Git Diff），罗列出本次更新迭代了哪些功能，并分别罗列这些新功能存在的优劣与风险。
要求：
1. 提取核心功能点，条理清晰。
2. 对每个功能点，分析其优点、缺点、潜在风险。
3. 语言专业、精炼。

Git Diff:
{diff}
"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个资深的研发专家和架构师，擅长Code Review和系统分析。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5
    }
    
    print(f"正在调用 {MODEL} 分析代码更新...")
    response = requests.post(f"{OPENAI_BASE_URL}/chat/completions", headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"API Error: {response.text}")
    
    return response.json()["choices"][0]["message"]["content"]

def send_feishu(content):
    if not FEISHU_WEBHOOK: return
    payload = {"msg_type": "text", "content": {"text": "🔔 WeKnora 同步与代码更新分析\n\n" + content}}
    requests.post(FEISHU_WEBHOOK, json=payload)

def send_dingtalk(content):
    if not DINGTALK_WEBHOOK: return
    payload = {"msgtype": "text", "text": {"content": "🔔 WeKnora 同步与代码更新分析\n\n" + content}}
    requests.post(DINGTALK_WEBHOOK, json=payload)

def send_wecom(content):
    if not WECOM_WEBHOOK: return
    payload = {"msgtype": "markdown", "markdown": {"content": "🔔 **WeKnora 同步与代码更新分析**\n\n" + content}}
    requests.post(WECOM_WEBHOOK, json=payload)

if __name__ == "__main__":
    try:
        diff_content = sync_and_get_diff()
        if diff_content:
            analysis_result = analyze_diff(diff_content)
            print("\n--- Analysis Result ---\n", analysis_result)
            send_feishu(analysis_result)
            send_dingtalk(analysis_result)
            send_wecom(analysis_result)
        else:
            print("没有检测到代码更新。")
    except Exception as e:
        print(f"执行失败: {e}")
        exit(1)