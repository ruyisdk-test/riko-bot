"""
Check CLI Command - 版本检查命令

本模块提供版本检查的 CLI 接口，将参数解析和服务调用分离。
"""

import logging

from ...services.check_service import CheckService

logger = logging.getLogger(__name__)


def check() -> None:
    """
    版本检查命令入口

    功能：调用 CheckService 执行版本检查
    """
    CheckService.run()
