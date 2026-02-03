"""
Manifests CLI Command - 清单生成命令

本模块提供清单生成的 CLI 接口，将参数解析和服务调用分离。
"""

import logging
from typing import List

from ...services.manifest_service import ManifestService

logger = logging.getLogger(__name__)


def manifests(up_name: str, gen_vers: List[str], down_grade: bool) -> None:
    """
    清单生成命令入口

    功能：调用 ManifestService 执行清单生成

    :param up_name: 上游包名
    :param gen_vers: 要生成的版本列表
    :param down_grade: 是否允许降级生成
    """
    ManifestService.generate(up_name, gen_vers, down_grade)
