# riko/cli/utils.py - CLI 工具函数模块
"""
提供通用的工具函数
"""

import os  # 操作系统接口模块（文件和目录操作）


# 目录操作工具函数
def ensure_dir(path: str) -> None:
    """
    确保目录存在，如果不存在则创建

    :param path: 目录路径（可以是字符串或 Path 对象）
    :return: None
    """
    # 检查路径是否存在
    if not os.path.exists(path):
        # os.makedirs() 递归创建目录
        # 如果父目录不存在，会自动创建父目录
        os.makedirs(path)
