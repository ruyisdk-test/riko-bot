#!/usr/bin/env python3
# riko/interfaces/cli/version_sync.py - 版本同步命令
"""
版本同步命令的 CLI 接口，将参数解析和服务调用分离。
"""

import argparse
import logging

from ...services.version_sync_service import VersionSyncService

logger = logging.getLogger(__name__)


def version_sync(args: argparse.Namespace) -> None:
    """
    版本同步命令入口

    功能：调用 VersionSyncService 执行版本同步

    :param args: Parsed command line arguments
    """
    VersionSyncService.sync_all(args)
