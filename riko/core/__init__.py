"""
Riko Core Layer - 核心业务逻辑层

本模块提供 Riko 项目的核心业务逻辑和数据模型。
这是整个项目的基础层，被服务层和接口层依赖。

主要导出：
- Riko: 核心业务类
- get_riko: 获取 Riko 单例的工厂函数
- RikoPkg: 包数据模型
- GithubUpstream: GitHub 上游源
- RegexUpstream: 正则表达式上游源
"""

from .riko import Riko, get_riko
from .models import RikoPkg, GithubUpstream, RegexUpstream

__all__ = [
    "Riko",
    "get_riko",
    "RikoPkg",
    "GithubUpstream",
    "RegexUpstream",
]
