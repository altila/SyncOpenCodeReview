"""
安全分析插件
检查代码中的安全漏洞、敏感信息泄露、注入风险等
"""
import re
from typing import Dict, List, Any
from .base import BaseAnalysisPlugin, AnalysisResult


class SecurityAnalysisPlugin(BaseAnalysisPlugin):
    """安全分析插件"""
    
    name = "security_analysis"
    description = "分析代码中的安全漏洞、敏感信息泄露、注入风险等安全问题"
    version = "1.0.0"
    author = "SyncOpenCodeReview Team"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        # 安全问题正则规则
        self.rules = {
            "sql_injection": [
                re.compile(r'(execute|query|raw)\s*\(\s*f["\'].*%s|{.*}.*["\']', re.IGNORECASE),
                re.compile(r'SELECT.*FROM.*\+|\+.*WHERE', re.IGNORECASE)
            ],
            "xss_vulnerability": [
                re.compile(r'(innerHTML|document\.write|eval\(|setTimeout\(|setInterval\()\s*\(.+user.*input', re.IGNORECASE),
                re.compile(r' dangerouslySetInnerHTML\s*=', re.IGNORECASE)
            ],
            "hardcoded_ip": [
                re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b(?!\.)')
            ],
            "path_traversal": [
                re.compile(r'(\.\./|\.\.\\)'),
                re.compile(r'open\s*\(\s*.*request\.', re.IGNORECASE)
            ],
            "weak_crypto": [
                re.compile(r'(md5|sha1|des|rc4)\s*\(', re.IGNORECASE),
                re.compile(r'const\s+.*_SECRET\s*=\s*["\'].*123456|passw0rd|secret["\']', re.IGNORECASE)
            ],
            "cors_misconfiguration": [
                re.compile(r'Access-Control-Allow-Origin\s*:\s*\*', re.IGNORECASE),
                re.compile(r'CORS_ALLOW_ALL_ORIGINS\s*=\s*True', re.IGNORECASE)
            ]
        }
    
    def analyze(self, commit_logs: List[str], diff_content: str, 
               project_info: Dict[str, Any], context: Dict[str, Any]) -> AnalysisResult:
        issues = []
        
        for rule_name, patterns in self.rules.items():
            for pattern in patterns:
                matches = pattern.finditer(diff_content)
                for match in matches:
                    # 排除误报
                    if self._is_false_positive(match.group(0), rule_name):
                        continue
                    
                    line_num = self._get_line_number(diff_content, match.start())
                    issue = {
                        "type": rule_name,
                        "line": line_num,
                        "content": match.group(0).strip(),
                        "severity": self._get_severity(rule_name),
                        "description": self._get_description(rule_name),
                        "recommendation": self._get_recommendation(rule_name)
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
        
        # 统计
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
                "risk_level": self._calculate_risk_level(unique_issues)
            }
        )
    
    def _get_line_number(self, content: str, position: int) -> int:
        """根据字符位置获取行号"""
        return content[:position].count('\n') + 1
    
    def _get_severity(self, rule_name: str) -> str:
        """获取规则的严重级别"""
        severity_map = {
            "sql_injection": "critical",
            "xss_vulnerability": "high",
            "hardcoded_ip": "medium",
            "path_traversal": "high",
            "weak_crypto": "medium",
            "cors_misconfiguration": "medium"
        }
        return severity_map.get(rule_name, "warning")
    
    def _get_description(self, rule_name: str) -> str:
        """获取规则的描述信息"""
        description_map = {
            "sql_injection": "存在SQL注入风险，用户输入可能直接拼接到SQL语句中",
            "xss_vulnerability": "存在XSS跨站脚本攻击风险，用户输入可能直接渲染到页面",
            "hardcoded_ip": "代码中存在硬编码的IP地址，可能导致环境兼容性问题",
            "path_traversal": "存在路径遍历漏洞，攻击者可能访问到服务器敏感文件",
            "weak_crypto": "使用了弱加密算法或弱密码，安全性不足",
            "cors_misconfiguration": "CORS配置过松，允许任意域名访问，可能导致数据泄露"
        }
        return description_map.get(rule_name, "")
    
    def _get_recommendation(self, rule_name: str) -> str:
        """获取修复建议"""
        recommendation_map = {
            "sql_injection": "使用参数化查询/预编译语句，禁止直接拼接用户输入到SQL",
            "xss_vulnerability": "对用户输入进行HTML转义，避免直接使用innerHTML等危险方法",
            "hardcoded_ip": "将IP地址配置到配置文件或环境变量中，不要硬编码在代码里",
            "path_traversal": "对用户传入的文件路径进行校验，限制在允许的目录范围内",
            "weak_crypto": "使用更安全的加密算法，如SHA-256、AES、RSA等，密钥使用强随机值",
            "cors_misconfiguration": "严格限制允许的域名，不要使用通配符*，尤其是包含敏感数据的接口"
        }
        return recommendation_map.get(rule_name, "")
    
    def _calculate_risk_level(self, issues: List[Dict]) -> str:
        """计算整体风险级别"""
        critical_count = sum(1 for issue in issues if issue['severity'] == 'critical')
        high_count = sum(1 for issue in issues if issue['severity'] == 'high')
        
        if critical_count > 0:
            return "critical"
        elif high_count > 0:
            return "high"
        elif len(issues) > 0:
            return "medium"
        else:
            return "low"
    
    def _is_false_positive(self, content: str, rule_name: str) -> bool:
        """检查是否是误报"""
        content_lower = content.lower()
        # 排除注释
        if '//' in content or '#' in content or '/*' in content or '<!--' in content:
            return True
        # 排除测试代码
        if 'test' in content_lower or 'spec' in content_lower or 'mock' in content_lower:
            return True
        # 排除示例
        if 'example' in content_lower or 'demo' in content_lower:
            return True
        return False
