#!/usr/bin/env python3
# riko/database/__init__.py - 数据库模块
"""
数据库模块，用于记录扫描历史

导出内容：
- models: 数据库模型（简化版 v2）
- db_manager: 数据库管理器
- get_database: 获取数据库实例的便捷函数
"""

from .models import (
    Base,
    ScanRecord,
    PackageUpdate,
    ManifestRecord,
    PRRecord
)

from .db_manager import DatabaseManager, get_database
from .recorder import (
    CommandRecorder,
    get_recorder,
    record_command,
    set_trigger_source,
    get_trigger_source,
)

__all__ = [
    # Models
    'Base',
    'ScanRecord',
    'PackageUpdate',
    'ManifestRecord',
    'PRRecord',
    # Database Manager
    'DatabaseManager',
    'get_database',
    # Recorder
    'CommandRecorder',
    'get_recorder',
    'record_command',
    'set_trigger_source',
    'get_trigger_source',
]
