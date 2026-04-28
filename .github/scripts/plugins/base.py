"""
插件基类定义
所有分析插件都需要继承这个基类并实现相应的接口
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class AnalysisResult:
    """分析结果封装类"""
    
    def __init__(self, plugin_name: str, success: bool = True, 
                 data: Optional[Dict[str, Any]] = None, 
                 error_message: Optional[str] = None):
        self.plugin_name = plugin_name
        self.success = success
        self.data = data or {}
        self.error_message = error_message
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "plugin_name": self.plugin_name,
            "success": self.success,
            "data": self.data,
            "error_message": self.error_message
        }
    
    def __str__(self) -> str:
        if self.success:
            return f"[{self.plugin_name}] 分析成功: {len(self.data)} 条结果"
        else:
            return f"[{self.plugin_name}] 分析失败: {self.error_message}"


class BaseAnalysisPlugin(ABC):
    """分析插件基类"""
    
    # 插件元数据，子类必须设置
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.enabled: bool = self.config.get("enabled", True)
    
    @abstractmethod
    def analyze(self, commit_logs: List[str], diff_content: str, 
               project_info: Dict[str, Any], context: Dict[str, Any]) -> AnalysisResult:
        """
        执行分析逻辑，子类必须实现这个方法
        :param commit_logs: 提交日志列表
        :param diff_content: 代码差异内容
        :param project_info: 项目信息字典，包含项目名称、仓库地址等
        :param context: 上下文信息，可以在多个插件之间共享数据
        :return: 分析结果对象
        """
        pass
    
    def pre_analyze(self, commit_logs: List[str], diff_content: str, 
                   project_info: Dict[str, Any], context: Dict[str, Any]) -> None:
        """
        分析前钩子，子类可以选择性实现
        :param commit_logs: 提交日志列表
        :param diff_content: 代码差异内容
        :param project_info: 项目信息字典
        :param context: 上下文信息
        """
        pass
    
    def post_analyze(self, result: AnalysisResult, context: Dict[str, Any]) -> None:
        """
        分析后钩子，子类可以选择性实现
        :param result: 分析结果
        :param context: 上下文信息
        """
        pass
    
    def get_info(self) -> Dict[str, str]:
        """获取插件信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "enabled": str(self.enabled)
        }
