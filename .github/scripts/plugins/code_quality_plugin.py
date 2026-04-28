"""
代码质量分析插件
检查代码中的潜在质量问题、坏味道、性能问题等
"""
import re
from typing import Dict, List, Any
from .base import BaseAnalysisPlugin, AnalysisResult


class CodeQualityAnalysisPlugin(BaseAnalysisPlugin):
    """代码质量分析插件"""
    
    name = "code_quality"
    description = "分析代码中的质量问题，包括坏味道、潜在Bug、性能问题等"
    version = "1.0.0"
    author = "SyncOpenCodeReview Team"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        # 代码坏味道正则规则
        self.rules = {
            "hardcoded_secret": [
                re.compile(r'(password|secret|key|token|auth)[\s_]*=[\s_]*["\'][^"\']+["\']', re.IGNORECASE),
                re.compile(r'(AKIA|SK_|aws_secret_access_key|api_key)', re.IGNORECASE)
            ],
            "todo_comment": [
                re.compile(r'//\s*(TODO|FIXME|BUG|HACK|XXX):?.*', re.IGNORECASE),
                re.compile(r'#\s*(TODO|FIXME|BUG|HACK|XXX):?.*', re.IGNORECASE)
            ],
            "debug_code": [
                re.compile(r'(console\.log|print|debugger|alert\()', re.IGNORECASE)
            ],
            "large_function": [
                re.compile(r'(def|function|fn|func)\s+\w+\s*\([^)]*\)\s*\{[^}]{500,}\}', re.DOTALL)
            ],
            "unused_import": [
                re.compile(r'(import|from.*import)\s+.*[\s,](unused|_)\s*', re.IGNORECASE)
            ]
        }
    
    def analyze(self, commit_logs: List[str], diff_content: str, 
               project_info: Dict[str, Any], context: Dict[str, Any]) -> AnalysisResult:
        issues = []
        
        for rule_name, patterns in self.rules.items():
            for pattern in patterns:
                matches = pattern.finditer(diff_content)
                for match in matches:
                    # 获取匹配行的位置
                    line_num = self._get_line_number(diff_content, match.start())
                    issue = {
                        "type": rule_name,
                        "line": line_num,
                        "content": match.group(0).strip(),
                        "severity": self._get_severity(rule_name),
                        "description": self._get_description(rule_name)
                    }
                    issues.append(issue)
        
        # 去重
        unique_issues = []
        seen = set()
        for issue in issues:
            key = f"{issue['type']}_{issue['line']}_{issue['content']}"
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)
        
        # 统计各类问题数量
        stats = {}
        for issue in unique_issues:
            issue_type = issue['type']
            stats[issue_type] = stats.get(issue_type, 0) + 1
        
        return AnalysisResult(
            plugin_name=self.name,
            success=True,
            data={
                "issues": unique_issues,
                "total_issues": len(unique_issues),
                "stats": stats,
                "severity_counts": self._count_by_severity(unique_issues)
            }
        )
    
    def _get_line_number(self, content: str, position: int) -> int:
        """根据字符位置获取行号"""
        return content[:position].count('\n') + 1
    
    def _get_severity(self, rule_name: str) -> str:
        """获取规则的严重级别"""
        severity_map = {
            "hardcoded_secret": "critical",
            "debug_code": "warning",
            "todo_comment": "info",
            "large_function": "warning",
            "unused_import": "info"
        }
        return severity_map.get(rule_name, "warning")
    
    def _get_description(self, rule_name: str) -> str:
        """获取规则的描述信息"""
        description_map = {
            "hardcoded_secret": "代码中存在硬编码的密钥/敏感信息，可能导致安全漏洞",
            "debug_code": "代码中包含调试代码，不应该提交到生产环境",
            "todo_comment": "代码中包含TODO/FIXME等待办注释，需要后续处理",
            "large_function": "函数/方法过长（超过500行），建议拆分",
            "unused_import": "存在未使用的导入，建议清理"
        }
        return description_map.get(rule_name, "")
    
    def _count_by_severity(self, issues: List[Dict]) -> Dict[str, int]:
        """按严重级别统计问题数量"""
        counts = {"critical": 0, "warning": 0, "info": 0}
        for issue in issues:
            counts[issue['severity']] += 1
        return counts
