"""
分析历史管理模块
用于记录和管理已经分析过的提交，实现增量分析能力
"""
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Set


class AnalysisHistory:
    """分析历史管理类"""
    
    def __init__(self, history_dir: str = ".github/analysis_history"):
        self.history_dir = history_dir
        os.makedirs(history_dir, exist_ok=True)
    
    def _get_history_file_path(self, project_name: str) -> str:
        """获取指定项目的历史记录文件路径"""
        safe_project_name = project_name.lower().replace(" ", "_").replace("/", "_")
        return os.path.join(self.history_dir, f"{safe_project_name}.json")
    
    def load_history(self, project_name: str) -> Dict:
        """加载指定项目的分析历史记录"""
        history_file = self._get_history_file_path(project_name)
        if not os.path.exists(history_file):
            return {
                "project_name": project_name,
                "last_analysis_time": None,
                "analyzed_commits": [],
                "analysis_records": []
            }
        
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载分析历史记录失败: {e}")
            return {
                "project_name": project_name,
                "last_analysis_time": None,
                "analyzed_commits": [],
                "analysis_records": []
            }
    
    def save_history(self, project_name: str, history: Dict) -> None:
        """保存指定项目的分析历史记录"""
        history_file = self._get_history_file_path(project_name)
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            print(f"✅ 分析历史记录已保存到: {history_file}")
        except Exception as e:
            print(f"⚠️ 保存分析历史记录失败: {e}")
    
    def get_unanalyzed_commits(self, project_name: str, all_commits: List[str]) -> List[str]:
        """
        获取还没有分析过的提交列表
        :param project_name: 项目名称
        :param all_commits: 所有待检查的提交哈希列表
        :return: 还没有分析过的提交哈希列表
        """
        history = self.load_history(project_name)
        analyzed_commits: Set[str] = set(history.get("analyzed_commits", []))
        return [commit for commit in all_commits if commit not in analyzed_commits]
    
    def mark_commits_analyzed(self, project_name: str, commits: List[str], 
                              analysis_time: Optional[str] = None, 
                              report_path: Optional[str] = None) -> None:
        """
        标记提交为已分析
        :param project_name: 项目名称
        :param commits: 已分析的提交哈希列表
        :param analysis_time: 分析时间，默认使用当前时间
        :param report_path: 分析报告路径
        """
        if analysis_time is None:
            analysis_time = datetime.now().isoformat()
        
        history = self.load_history(project_name)
        
        # 添加到已分析提交列表
        analyzed_commits = set(history.get("analyzed_commits", []))
        for commit in commits:
            analyzed_commits.add(commit)
        history["analyzed_commits"] = list(analyzed_commits)
        
        # 更新最后分析时间
        history["last_analysis_time"] = analysis_time
        
        # 添加分析记录
        if "analysis_records" not in history:
            history["analysis_records"] = []
        
        history["analysis_records"].append({
            "time": analysis_time,
            "commits": commits,
            "report_path": report_path
        })
        
        # 只保留最近100条分析记录
        if len(history["analysis_records"]) > 100:
            history["analysis_records"] = history["analysis_records"][-100:]
        
        # 只保留最近1000个已分析提交哈希
        if len(history["analyzed_commits"]) > 1000:
            history["analyzed_commits"] = history["analyzed_commits"][-1000:]
        
        self.save_history(project_name, history)
    
    def get_last_analysis_commit(self, project_name: str) -> Optional[str]:
        """获取上次分析的最后一个提交哈希"""
        history = self.load_history(project_name)
        analyzed_commits = history.get("analyzed_commits", [])
        return analyzed_commits[-1] if analyzed_commits else None


# 全局实例
analysis_history = AnalysisHistory()
