#!/usr/bin/env python3
# riko/interfaces/cli/version_sync.py - 版本同步命令
"""
版本同步命令的 CLI 接口，将参数解析和服务调用分离。
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

from ...services.version_sync_service import VersionSyncService

logger = logging.getLogger(__name__)


def version_sync(args: argparse.Namespace) -> None:
    """
    版本同步命令入口

    功能：调用 VersionSyncService 执行版本同步

    :param args: Parsed command line arguments
    """
    # 如果是 dry-run 模式，将日志同时输出到文件
    if getattr(args, 'dry_run', False):
        dry_run_docs_dir = Path(__file__).parent.parent.parent.parent / "version-dry-run_docs"
        dry_run_docs_dir.mkdir(parents=True, exist_ok=True)

        # 生成带时间戳的日志文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = dry_run_docs_dir / f"version-sync-{timestamp}.log"

        # 获取根 logger 并添加文件 handler
        root_logger = logging.getLogger()
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root_logger.addHandler(file_handler)

        # 将日志同时输出到 stdout
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.INFO)
        stdout_handler.setFormatter(logging.Formatter('%(message)s'))
        root_logger.addHandler(stdout_handler)

        logger.info(f"Dry-run logs will be saved to: {log_file}")

    VersionSyncService.sync_all(args)
