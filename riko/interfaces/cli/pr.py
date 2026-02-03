#!/usr/bin/env python3
# riko/cli/pr.py - GitHub PR 创建命令
"""
提供 PR 创建的 CLI 接口，将参数解析和服务调用分离。
"""

import argparse
import logging

from ...services.pr_service import PRService

logger = logging.getLogger(__name__)


def pr(args: argparse.Namespace) -> None:
    """
    PR 创建命令入口

    功能：调用 PRService 执行 PR 创建

    :param args: Parsed command line arguments
    """
    PRService.create(args)
