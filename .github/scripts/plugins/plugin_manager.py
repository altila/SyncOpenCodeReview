"""
插件管理器
负责插件的加载、注册、执行和管理
"""
import os
import importlib
from typing import Dict, List, Type, Optional, Any
from .base import BaseAnalysisPlugin, AnalysisResult


class PluginManager:
    """插件管理器类"""
    
    def __init__(self, plugins_dir: str = None):
        if plugins_dir is None:
            plugins_dir = os.path.dirname(os.path.abspath(__file__))
        self.plugins_dir = plugins_dir
        self.plugins: Dict[str, BaseAnalysisPlugin] = {}
        self._loaded = False
    
    def load_plugins(self, config: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        """
        加载所有插件
        :param config: 插件配置字典，key是插件名称，value是插件配置
        """
        if self._loaded:
            return
        
        config = config or {}
        plugin_files = [f for f in os.listdir(self.plugins_dir) 
                       if f.endswith('.py') and not f.startswith('_') and f != 'base.py']
        
        for plugin_file in plugin_files:
            module_name = plugin_file[:-3]
            try:
                # 导入插件模块
                module = importlib.import_module(f'.{module_name}', package=__package__)
                # 查找插件类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, BaseAnalysisPlugin) and 
                        attr != BaseAnalysisPlugin):
                        # 获取插件配置
                        plugin_config = config.get(attr.name, {})
                        # 实例化插件
                        plugin_instance = attr(plugin_config)
                        if plugin_instance.enabled:
                            self.plugins[plugin_instance.name] = plugin_instance
                            print(f"✅ 加载插件成功: {plugin_instance.name} v{plugin_instance.version}")
                        else:
                            print(f"ℹ️ 插件已禁用: {attr.name}")
                            
            except Exception as e:
                print(f"❌ 加载插件失败 {plugin_file}: {e}")
                import traceback
                traceback.print_exc()
        
        self._loaded = True
        print(f"📦 共加载 {len(self.plugins)} 个可用插件")
    
    def get_plugin(self, plugin_name: str) -> Optional[BaseAnalysisPlugin]:
        """
        根据名称获取插件实例
        :param plugin_name: 插件名称
        :return: 插件实例，不存在返回None
        """
        if not self._loaded:
            self.load_plugins()
        return self.plugins.get(plugin_name)
    
    def get_all_plugins(self) -> List[BaseAnalysisPlugin]:
        """
        获取所有已加载的插件
        :return: 插件实例列表
        """
        if not self._loaded:
            self.load_plugins()
        return list(self.plugins.values())
    
    def run_all_plugins(self, commit_logs: List[str], diff_content: str, 
                       project_info: Dict[str, Any], 
                       run_disabled: bool = False) -> List[AnalysisResult]:
        """
        运行所有已启用的插件
        :param commit_logs: 提交日志列表
        :param diff_content: 代码差异内容
        :param project_info: 项目信息字典
        :param run_disabled: 是否运行被禁用的插件，默认False
        :return: 所有插件的分析结果列表
        """
        if not self._loaded:
            self.load_plugins()
        
        results = []
        context = {}
        
        for plugin in self.plugins.values():
            if not plugin.enabled and not run_disabled:
                continue
            
            print(f"🔍 运行插件: {plugin.name}")
            try:
                # 执行前置钩子
                plugin.pre_analyze(commit_logs, diff_content, project_info, context)
                # 执行分析
                result = plugin.analyze(commit_logs, diff_content, project_info, context)
                # 执行后置钩子
                plugin.post_analyze(result, context)
                
                results.append(result)
                print(f"✅ 插件 {plugin.name} 执行完成: {result}")
                
            except Exception as e:
                print(f"❌ 插件 {plugin.name} 执行失败: {e}")
                import traceback
                traceback.print_exc()
                results.append(AnalysisResult(
                    plugin_name=plugin.name,
                    success=False,
                    error_message=str(e)
                ))
        
        return results
    
    def run_plugin(self, plugin_name: str, commit_logs: List[str], diff_content: str,
                  project_info: Dict[str, Any]) -> Optional[AnalysisResult]:
        """
        运行指定名称的插件
        :param plugin_name: 插件名称
        :param commit_logs: 提交日志列表
        :param diff_content: 代码差异内容
        :param project_info: 项目信息字典
        :return: 分析结果，插件不存在或执行失败返回None
        """
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            print(f"❌ 插件不存在: {plugin_name}")
            return None
        
        context = {}
        try:
            plugin.pre_analyze(commit_logs, diff_content, project_info, context)
            result = plugin.analyze(commit_logs, diff_content, project_info, context)
            plugin.post_analyze(result, context)
            return result
        except Exception as e:
            print(f"❌ 插件 {plugin_name} 执行失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def reload_plugins(self, config: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        """
        重新加载所有插件
        :param config: 新的插件配置
        """
        self.plugins.clear()
        self._loaded = False
        self.load_plugins(config)
        print(f"🔄 插件已重新加载，共 {len(self.plugins)} 个可用插件")


# 全局插件管理器实例
plugin_manager = PluginManager()
