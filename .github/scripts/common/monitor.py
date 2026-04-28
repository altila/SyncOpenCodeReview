"""
监控告警模块
负责收集执行指标、异常告警、状态统计
"""
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from .utils import send_webhook, build_webhook_payload


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"


class AlertLevel(Enum):
    """告警级别枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class TaskMetric:
    """任务指标数据类"""
    task_id: str
    task_name: str
    project_name: Optional[str]
    status: TaskStatus
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    llm_calls: int = 0
    llm_fallback_count: int = 0
    llm_total_tokens: int = 0
    plugins_executed: int = 0
    plugins_failed: int = 0
    issues_found: int = 0
    error_message: Optional[str] = None
    extra: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['status'] = self.status.value
        if self.extra is None:
            data['extra'] = {}
        return data


class Monitor:
    """监控管理器"""
    
    def __init__(self, metrics_dir: str = ".github/metrics", 
                alert_config: Optional[Dict[str, Any]] = None):
        self.metrics_dir = metrics_dir
        os.makedirs(metrics_dir, exist_ok=True)
        
        # 默认告警配置
        self.alert_config = alert_config or {
            "enabled": True,
            "alert_on_failure": True,
            "alert_on_llm_fallback": True,
            "alert_on_security_issue": True,
            "min_alert_level": AlertLevel.WARNING.value,
            "webhook_channels": ["feishu", "dingtalk", "wecom"]
        }
        
        self.current_tasks: Dict[str, TaskMetric] = {}
    
    def start_task(self, task_name: str, project_name: Optional[str] = None) -> str:
        """
        开始一个任务，生成任务ID并记录开始时间
        :param task_name: 任务名称
        :param project_name: 项目名称
        :return: 任务ID
        """
        task_id = f"{int(time.time())}_{task_name.replace(' ', '_')}"
        metric = TaskMetric(
            task_id=task_id,
            task_name=task_name,
            project_name=project_name,
            status=TaskStatus.RUNNING,
            start_time=time.time(),
            extra={}
        )
        self.current_tasks[task_id] = metric
        print(f"🔍 开始任务: {task_name} (ID: {task_id})")
        return task_id
    
    def end_task(self, task_id: str, status: TaskStatus, 
                error_message: Optional[str] = None,
                extra: Optional[Dict[str, Any]] = None) -> TaskMetric:
        """
        结束任务，记录结束时间和状态
        :param task_id: 任务ID
        :param status: 任务状态
        :param error_message: 错误信息（如果失败）
        :param extra: 额外数据
        :return: 完整的任务指标
        """
        if task_id not in self.current_tasks:
            raise ValueError(f"任务不存在: {task_id}")
        
        metric = self.current_tasks[task_id]
        metric.status = status
        metric.end_time = time.time()
        metric.duration = round(metric.end_time - metric.start_time, 2)
        metric.error_message = error_message
        
        if extra:
            metric.extra.update(extra)
        
        # 保存指标
        self._save_metric(metric)
        
        # 检查是否需要告警
        if self.alert_config.get("enabled", True):
            self._check_and_alert(metric)
        
        # 从当前任务中移除
        del self.current_tasks[task_id]
        
        status_str = "✅ 成功" if status == TaskStatus.SUCCESS else "❌ 失败" if status == TaskStatus.FAILED else "⚠️ 部分成功"
        print(f"{status_str} 任务结束: {metric.task_name} (ID: {task_id}), 耗时: {metric.duration}s")
        
        return metric
    
    def update_task_metric(self, task_id: str, **kwargs) -> None:
        """
        更新任务指标
        :param task_id: 任务ID
        :param kwargs: 需要更新的字段，如llm_calls、issues_found等
        """
        if task_id not in self.current_tasks:
            return
        
        metric = self.current_tasks[task_id]
        for key, value in kwargs.items():
            if hasattr(metric, key):
                setattr(metric, key, value)
    
    def increment_metric(self, task_id: str, field: str, increment: int = 1) -> None:
        """
        递增指标值
        :param task_id: 任务ID
        :param field: 字段名
        :param increment: 递增数值
        """
        if task_id not in self.current_tasks:
            return
        
        metric = self.current_tasks[task_id]
        if hasattr(metric, field) and isinstance(getattr(metric, field), int):
            current_value = getattr(metric, field)
            setattr(metric, field, current_value + increment)
    
    def send_alert(self, level: AlertLevel, title: str, content: str, 
                  project_name: Optional[str] = None) -> None:
        """
        手动发送告警
        :param level: 告警级别
        :param title: 告警标题
        :param content: 告警内容
        :param project_name: 所属项目
        """
        if level.value < self.alert_config.get("min_alert_level", AlertLevel.WARNING.value):
            return
        
        print(f"🚨 [{level.value.upper()}] {title}: {content}")
        
        # 构造告警消息
        alert_content = f"""
# {level.value.upper()}告警: {title}

**告警级别**: {level.value.upper()}
**项目**: {project_name or '全局'}
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**内容**: {content}
        """
        
        # 发送到配置的Webhook渠道
        channels = self.alert_config.get("webhook_channels", [])
        for channel in channels:
            env_name = f"{channel.upper()}_WEBHOOK_URL"
            webhook_url = os.getenv(env_name)
            if webhook_url:
                payload = build_webhook_payload(
                    report=alert_content,
                    webhook_type=channel,
                    project_name="系统告警",
                    has_update=False
                )
                send_webhook(webhook_url, payload, channel.capitalize())
    
    def get_task_history(self, limit: int = 100, 
                        project_name: Optional[str] = None,
                        status: Optional[TaskStatus] = None) -> List[Dict[str, Any]]:
        """
        获取任务历史记录
        :param limit: 返回记录数量限制
        :param project_name: 按项目过滤
        :param status: 按状态过滤
        :return: 任务指标列表
        """
        metrics = []
        # 按时间倒序读取文件
        files = sorted(os.listdir(self.metrics_dir), reverse=True)[:limit]
        
        for file in files:
            if not file.endswith('.json'):
                continue
            file_path = os.path.join(self.metrics_dir, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    metric = json.load(f)
                    
                    # 过滤
                    if project_name and metric.get('project_name') != project_name:
                        continue
                    if status and metric.get('status') != status.value:
                        continue
                        
                    metrics.append(metric)
            except Exception:
                continue
        
        return metrics[:limit]
    
    def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        获取统计数据
        :param days: 统计最近多少天的数据
        :return: 统计结果
        """
        cutoff_time = time.time() - days * 86400
        total_tasks = 0
        success_count = 0
        failed_count = 0
        total_duration = 0
        total_llm_calls = 0
        total_issues = 0
        
        files = sorted(os.listdir(self.metrics_dir), reverse=True)
        for file in files:
            if not file.endswith('.json'):
                continue
            file_path = os.path.join(self.metrics_dir, file)
            try:
                mtime = os.path.getmtime(file_path)
                if mtime < cutoff_time:
                    break
                    
                with open(file_path, 'r', encoding='utf-8') as f:
                    metric = json.load(f)
                    total_tasks += 1
                    if metric['status'] == TaskStatus.SUCCESS.value:
                        success_count += 1
                    elif metric['status'] == TaskStatus.FAILED.value:
                        failed_count += 1
                    
                    if metric.get('duration'):
                        total_duration += metric['duration']
                    
                    total_llm_calls += metric.get('llm_calls', 0)
                    total_issues += metric.get('issues_found', 0)
                    
            except Exception:
                continue
        
        success_rate = round(success_count / total_tasks * 100, 2) if total_tasks > 0 else 0
        avg_duration = round(total_duration / total_tasks, 2) if total_tasks > 0 else 0
        
        return {
            "period_days": days,
            "total_tasks": total_tasks,
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": f"{success_rate}%",
            "average_duration": f"{avg_duration}s",
            "total_llm_calls": total_llm_calls,
            "total_issues_found": total_issues
        }
    
    def _save_metric(self, metric: TaskMetric) -> None:
        """保存指标到文件"""
        date_str = datetime.fromtimestamp(metric.start_time).strftime('%Y-%m-%d')
        date_dir = os.path.join(self.metrics_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)
        
        file_name = f"{metric.task_id}.json"
        file_path = os.path.join(date_dir, file_name)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(metric.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存指标失败: {e}")
    
    def _check_and_alert(self, metric: TaskMetric) -> None:
        """检查任务指标是否需要告警"""
        # 任务失败告警
        if self.alert_config.get("alert_on_failure", True) and metric.status == TaskStatus.FAILED:
            self.send_alert(
                level=AlertLevel.ERROR,
                title=f"任务执行失败: {metric.task_name}",
                content=f"项目: {metric.project_name or '全局'}\n错误信息: {metric.error_message or '未知错误'}\n耗时: {metric.duration}s",
                project_name=metric.project_name
            )
        
        # LLM降级告警
        if self.alert_config.get("alert_on_llm_fallback", True) and metric.llm_fallback_count > 0:
            self.send_alert(
                level=AlertLevel.WARNING,
                title=f"LLM服务降级",
                content=f"项目: {metric.project_name or '全局'}\n降级次数: {metric.llm_fallback_count}\n可能主LLM服务故障，已自动切换到备用LLM",
                project_name=metric.project_name
            )
        
        # 安全问题告警
        if self.alert_config.get("alert_on_security_issue", True) and metric.issues_found > 0:
            # 检查extra里是否有安全问题
            security_issues = metric.extra.get("security_issues", 0)
            if security_issues > 0:
                self.send_alert(
                    level=AlertLevel.CRITICAL,
                    title=f"发现安全漏洞: {metric.project_name}",
                    content=f"本次代码更新检测到 {security_issues} 个安全问题，请及时处理",
                    project_name=metric.project_name
                )


# 全局监控实例
monitor = Monitor()
