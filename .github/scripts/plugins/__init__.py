"""
插件化分析框架
支持动态加载和扩展各种分析能力
"""
from .base import BaseAnalysisPlugin, AnalysisResult
from .plugin_manager import plugin_manager, PluginManager

__all__ = [
    'BaseAnalysisPlugin',
    'AnalysisResult',
    'plugin_manager',
    'PluginManager'
]
