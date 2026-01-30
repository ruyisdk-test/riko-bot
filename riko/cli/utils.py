# riko/cli/utils.py - CLI 工具函数模块
"""
提供通用的工具函数（类似于 Java 的 Utils 类）
"""

import os  # 操作系统接口模块（文件和目录操作）


# ========== 目录操作工具函数 ==========
def ensure_dir(path: str) -> None:
    """
    确保目录存在，如果不存在则创建
    类似于 Java 的 Files.createDirectories() 或 FileUtils.forceMkdir()

    Python 特殊语法：
    - path: str 是类型注解（Type Hint），表示参数类型（可选）
    - -> None 表示返回类型注解（类似于 Java 的:void）

    :param path: 目录路径（可以是字符串或 Path 对象）
    :return: None
    """
    # os.path.exists() 检查路径是否存在（类似于 Java 的 Files.exists()）
    if not os.path.exists(path):
        # os.makedirs() 递归创建目录（类似于 Java 的 Files.createDirectories()）
        # 如果父目录不存在，会自动创建父目录
        os.makedirs(path)
