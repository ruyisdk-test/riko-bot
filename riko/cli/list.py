# riko/cli/list.py - 列出 nvchecker 检查结果
"""
实现 riko list 命令，用于查询和过滤 nvchecker 的检查结果
类似于 Java 的 Service 层方法
"""

import json  # JSON 处理库
import sys   # 系统模块（访问标准输入/输出）

from typing import Dict, List  # 类型注解

from ..rikoriko import get_riko  # 导入核心单例


def list_result(event: str) -> None:
    """
    列出 nvchecker 的检查结果

    支持的过滤条件：
    - 事件类型（event）：
      * "updated" - 发现新版本
      * "up-to-date" - 已是最新版本
      * "no-result" - 未获取到结果（通常表示检查失败）
    - 日志级别（level）：
      * "debug" - 调试信息
      * "info" - 一般信息
      * "error" - 错误信息
    - "any" - 显示所有结果

    :param event: 过滤条件（事件类型或日志级别）
    :return: None（结果直接输出到 stdout）

    Python 特殊语法：
    - sys.stdout: 标准输出流（类似于 Java 的 System.out）
    - json.dump(): 将对象序列化为 JSON 并输出（类似于 Java 的 Jackson ObjectMapper）
    """
    # 获取过滤后的结果列表
    # get_riko() 返回单例，调用其方法获取数据
    res: List[Dict] = get_riko().get_nvchecker_results(event)

    # 将结果 JSON 序列化到标准输出
    # sys.stdout 表示标准输出流（类似于 Java 的 System.out）
    # indent=2 美化格式（2 空格缩进）
    # sort_keys=False 保持键的原始顺序（不按字母排序）
    json.dump(res, sys.stdout, indent=2, sort_keys=False)
