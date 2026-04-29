import os
import sys
from datetime import datetime

# 导入通用LLM模块
from llm_utils import ModelConfig, ModelFactory, BaseModelClient
from llm_clients import GENAI_AVAILABLE

# 导入公共Webhook模块
from webhook_utils import send_all_webhooks

# 报告目录配置
REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")
SAVE_SUMMARY = os.getenv("SAVE_SUMMARY", "true").lower() == "true"


def read_file(filepath):
    """读取文件内容"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"⚠️ 读取文件 {filepath} 失败: {e}")
        return None





def collect_daily_reports(date_str=None):
    """收集指定日期的所有项目汇总报告"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    reports = []
    if not os.path.exists(REPORTS_DIR):
        print(f"⚠️ 报告目录 {REPORTS_DIR} 不存在")
        return reports
    
    # 遍历所有项目目录
    for project_dir in os.listdir(REPORTS_DIR):
        project_path = os.path.join(REPORTS_DIR, project_dir)
        if not os.path.isdir(project_path) or project_dir == "daily-summary" or project_dir == "modules":
            continue
        
        # 查找当天的汇总报告
        summary_file = os.path.join(project_path, f"{date_str}-汇总.md")
        if os.path.exists(summary_file):
            content = read_file(summary_file)
            if content:
                reports.append({
                    "project_name": project_dir.replace("-", " ").title(),
                    "file_path": summary_file,
                    "content": content
                })
                print(f"✅ 读取到 {project_dir} 的汇总报告")
    
    return reports


def collect_module_reports(date_str=None):
    """收集指定日期的所有项目模块报告，按模块名称分组"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    module_reports = {}
    if not os.path.exists(REPORTS_DIR):
        print(f"⚠️ 报告目录 {REPORTS_DIR} 不存在")
        return module_reports
    
    # 遍历所有项目目录
    for project_dir in os.listdir(REPORTS_DIR):
        project_path = os.path.join(REPORTS_DIR, project_dir)
        if not os.path.isdir(project_path) or project_dir == "daily-summary" or project_dir == "modules":
            continue
        
        # 查找当天的所有模块报告
        for filename in os.listdir(project_path):
            if filename.startswith(date_str) and filename.endswith(".md") and "-汇总.md" not in filename and "-无更新.md" not in filename:
                # 提取模块名称：YYYY-MM-DD-模块名称.md -> 模块名称
                module_name = filename[len(date_str)+1:-3].replace("-", " ").title()
                file_path = os.path.join(project_path, filename)
                content = read_file(file_path)
                
                if content:
                    if module_name not in module_reports:
                        module_reports[module_name] = []
                    
                    module_reports[module_name].append({
                        "project_name": project_dir.replace("-", " ").title(),
                        "file_path": file_path,
                        "content": content
                    })
                    print(f"✅ 读取到 {project_dir} 的 {module_name} 模块报告")
    
    return module_reports


def analyze_all_reports(reports, model_client: BaseModelClient):
    """调用大模型汇总分析所有报告"""
    # 构建提示词
    reports_content = ""
    for idx, report in enumerate(reports, 1):
        reports_content += f"""
        === 项目 {idx}: {report['project_name']} ===
        {report['content']}
        
        """
    
    prompt = f"""
    你是一个资深的架构师和技术分析师。以下是今日所有开源项目的代码更新分析报告。
    
    {reports_content}
    
    请你根据所有报告内容，输出一份汇总分析报告，必须包含以下几个部分：
    
    1. **今日更新总览**：
       - 统计今日有更新的项目数量
       - 简要描述今日所有项目的核心更新方向
    
    2. **功能亮点汇总**：
       - 按项目分类，列出每个项目最有价值的新增功能、优化点
       - 每个功能点标注对应的代码文件路径（从原报告中提取）
    
    3. **风险与问题汇总**：
       - 汇总所有项目中发现的潜在问题、技术债务、安全隐患
       - 标注问题所属项目和相关文件位置
    
    4. **技术趋势观察**：
       - 分析今日所有更新中体现出来的技术趋势、共性优化方向
       - 给出相关的技术建议
    
    注意：
    - 所有文件路径必须准确，保留原报告中的路径信息
    - 突出重点，避免重复信息
    - 语言简洁明了，结构清晰
    - 对于重要的功能和问题，可以适当高亮标注
    """
    
    # 使用模型客户端生成内容
    return model_client.generate(prompt, temperature=0.3, timeout=120)


def analyze_module_reports(module_name, reports, model_client: BaseModelClient):
    """调用大模型分析单个模块的所有项目报告"""
    # 构建提示词
    reports_content = ""
    for idx, report in enumerate(reports, 1):
        reports_content += f"""
        === 项目 {idx}: {report['project_name']} ===
        {report['content']}
        
        """
    
    prompt = f"""
    你是一个资深的架构师和技术分析师。以下是今日所有项目中关于「{module_name}」模块的代码更新分析报告。
    
    {reports_content}
    
    请你根据所有报告内容，输出一份「{module_name}」模块的汇总分析报告，必须包含以下几个部分：
    
    1. **模块更新总览**：
       - 统计今日有多少个项目更新了该模块
       - 简要描述该模块今日的整体更新方向
    
    2. **核心更新明细**：
       - 按项目分类，列出每个项目中该模块的具体更新内容
       - 每个更新点标注对应的代码文件路径
       - 标注是新增功能、修复还是优化
    
    3. **优劣分析**：
       - 汇总该模块今日更新中的优秀实践、亮点设计
       - 指出存在的潜在问题、技术债务或可以优化的地方
    
    4. **跨项目对比与建议**：
       - 对比不同项目中该模块的实现差异
       - 给出通用的优化建议和最佳实践参考
    
    注意：
    - 所有文件路径必须准确，保留原报告中的路径信息
    - 突出重点，避免重复信息
    - 语言简洁明了，结构清晰
    """
    
    # 使用模型客户端生成内容
    return model_client.generate(prompt, temperature=0.3, timeout=120)


def save_summary_report(summary_content, date_str=None):
    """保存全项目汇总报告到文件"""
    if not SAVE_SUMMARY:
        print("ℹ️ 汇总报告保存功能已禁用")
        return None
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    try:
        summary_dir = os.path.join(REPORTS_DIR, "daily-summary")
        os.makedirs(summary_dir, exist_ok=True)
        
        filename = f"{date_str}-全项目汇总.md"
        filepath = os.path.join(summary_dir, filename)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        content = f"""# 📊 每日全项目代码更新汇总分析 - {date_str}

> 生成时间: {current_time}
> 今日更新项目数: {len(collect_daily_reports(date_str))}

---

{summary_content}

---

*本报告由 SyncOpenCodeReview 自动生成*
"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"✅ 全项目汇总报告已保存到: {filepath}")
        return filepath
    except Exception as e:
        print(f"⚠️ 保存全项目汇总报告失败: {e}")
        return None


def save_module_summary(module_name, module_content, date_str=None):
    """保存单个模块的汇总报告到文件"""
    if not SAVE_SUMMARY:
        print("ℹ️ 模块报告保存功能已禁用")
        return None
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    try:
        module_dir = os.path.join(REPORTS_DIR, "modules", module_name.replace(" ", "-").lower())
        os.makedirs(module_dir, exist_ok=True)
        
        filename = f"{date_str}-{module_name.replace(' ', '-')}.md"
        filepath = os.path.join(module_dir, filename)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        content = f"""# 📦 {module_name} 模块每日更新汇总 - {date_str}

> 生成时间: {current_time}
> 今日更新该模块的项目数: {len(collect_module_reports(date_str).get(module_name, []))}

---

{module_content}

---

*本报告由 SyncOpenCodeReview 自动生成*
"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"✅ 模块报告已保存到: {filepath}")
        return filepath
    except Exception as e:
        print(f"⚠️ 保存 {module_name} 模块报告失败: {e}")
        return None


def write_github_summary(report):
    """将报告写入 GitHub Actions Summary"""
    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary_file:
        try:
            with open(step_summary_file, "a", encoding="utf-8") as f:
                f.write(f"## 📊 每日全项目代码更新汇总分析\n\n")
                f.write(report)
            print("✅ 报告已写入 GitHub Step Summary")
        except Exception as e:
            print(f"⚠️ 写入 GitHub Step Summary 失败: {e}")


def main():
    print("=" * 60)
    print("📊 每日全项目代码更新汇总分析工具")
    print("=" * 60)
    
    # 初始化配置
    config = ModelConfig()
    
    # 检查模型配置
    active_provider = config.get_active_provider()
    if not active_provider:
        print("❌ 错误: 未配置任何有效的模型")
        print("   请设置 GEMINI_API_KEY 或 LLM_API_KEY 环境变量")
        return 1
    
    print(f"🔧 模型提供商: {active_provider}")
    
    # 收集当天的所有报告
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n📂 开始收集 {today} 的所有项目报告...")
    reports = collect_daily_reports(today)
    
    if not reports:
        print("ℹ️ 今日没有找到任何项目的分析报告，退出")
        return 0
    
    print(f"✅ 共收集到 {len(reports)} 个项目的报告")
    
    # 创建模型客户端
    model_client = ModelFactory.create_client(config)
    if not model_client:
        return 1
    
    model_info = model_client.get_model_info()
    print(f"   提供商: {model_info['provider']}")
    print(f"   模型: {model_info['model']}")
    
    # 调用大模型汇总分析（全项目）
    print("\n🤖 开始汇总分析所有项目报告...")
    summary_report = analyze_all_reports(reports, model_client)
    
    if not summary_report:
        print("❌ 全项目汇总分析失败")
        return 1
    
    print("✅ 全项目汇总分析完成")
    
    # 写入 GitHub Summary
    write_github_summary(summary_report)
    
    # 保存全项目汇总报告
    print("\n💾 保存全项目汇总报告...")
    save_summary_report(summary_report, today)
    
    # ========== 新增：按功能模块汇总 ==========
    print("\n📦 开始按功能模块汇总分析...")
    module_reports = collect_module_reports(today)
    
    if module_reports:
        print(f"✅ 共发现 {len(module_reports)} 个功能模块有更新")
        
        module_success_count = 0
        for module_name, module_reports_list in module_reports.items():
            print(f"\n🤖 分析 {module_name} 模块 ({len(module_reports_list)} 个项目)...")
            module_summary = analyze_module_reports(module_name, module_reports_list, model_client)
            
            if module_summary:
                save_module_summary(module_name, module_summary, today)
                module_success_count += 1
                print(f"✅ {module_name} 模块分析完成")
            else:
                print(f"⚠️ {module_name} 模块分析失败")
        
        print(f"\n📊 模块分析完成: {module_success_count}/{len(module_reports)} 成功")
    else:
        print("ℹ️ 今日没有发现任何功能模块报告，跳过模块汇总")
    # ==========================================
    
    # 发送 Webhook 通知（保持原有的全项目汇总通知不变）
    print("\n📤 发送全项目汇总通知...")
    success_count = send_all_webhooks(summary_report, title="📊 每日全项目代码更新汇总分析")

    print(f"\n📊 通知发送完成: {success_count}/3 成功")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
