"""
插件配置文件
配置各个插件的启用状态和参数
"""

PLUGIN_CONFIG = {
    # 代码质量分析插件
    "code_quality": {
        "enabled": True,
        "rules": {
            "hardcoded_secret": True,
            "todo_comment": True,
            "debug_code": True,
            "large_function": True,
            "unused_import": True
        }
    },
    
    # 安全分析插件
    "security_analysis": {
        "enabled": True,
        "rules": {
            "sql_injection": True,
            "xss_vulnerability": True,
            "hardcoded_ip": True,
            "path_traversal": True,
            "weak_crypto": True,
            "cors_misconfiguration": True
        },
        "severity_filter": ["critical", "high", "medium"]  # 只报告这几个级别的问题
    },
    
    # 更多插件可以在这里添加配置
    # "dependency_check": {
    #     "enabled": True,
    #     "vulnerability_db_url": "https://osv.dev/api"
    # },
    # "performance_analysis": {
    #     "enabled": False,
    #     "threshold": 0.8
    # }
}

# 是否启用插件系统
ENABLE_PLUGINS = True

# 插件执行超时时间（秒）
PLUGIN_EXECUTION_TIMEOUT = 30
