# riko/nvchecker/results.py - nvchecker 结果解析
"""
处理 nvchecker 工具输出的 JSON 结果文件
提供查询和过滤功能
类似于 Java 的 Repository + Service 层
"""

import json
import os

from pathlib import Path  # 路径操作
from typing import Dict, List  # 类型注解


class NvcheckerResults:
    """
    nvchecker 结果数据类
    负责加载和查询版本检查结果
    """

    # ========== 构造函数 ==========
    def __init__(self, path: Path):
        """
        初始化 NvcheckerResults 对象

        :param path: nvchecker 结果 JSON 文件路径（通常是 result.json）
        """
        self._path: Path = path  # 私有字段：结果文件路径
        self._data: List[Dict] = []  # 私有字段：加载后的数据列表

    # ========== 加载数据 ==========
    def load(self) -> None:
        """
        从 JSON 文件加载 nvchecker 结果

        :raises FileNotFoundError: 如果结果文件不存在

        Python 特殊语法：
        - with open() as f: 上下文管理器（自动关闭文件）
        - json.load(f): 从文件对象解析 JSON（类似于 Java 的 Jackson ObjectMapper）
        """
        # 检查文件是否存在
        if not os.path.exists(self._path):
            raise FileNotFoundError(self._path)

        # 读取并解析 JSON 文件
        # 默认以 "r" 模式打开（文本读取模式）
        with open(self._path) as f:
            content = f.read()
            # 处理空文件（首次运行或 nvchecker 未生成结果）
            if not content or content.strip() == "":
                self._data = []
                return
            self._data = json.loads(content)  # 解析为 Python 对象（列表）

    # ========== 查询方法 ==========
    def get_data(self) -> List[Dict]:
        """
        获取所有结果数据（不过滤）

        :return: 完整的结果字典列表
        """
        return self._data

    def get_event_data(self, event_or_level: str) -> List[Dict]:
        """
        根据 event 或 level 过滤结果

        nvchecker JSON 结构示例：
        {
          "name": "LicheeRV-Nano-Build",
          "event": "updated",
          "level": "info",
          "version": "0.20260114.0"
        }

        支持的过滤条件：
        - event: "updated", "up-to-date", "no-result"
        - level: "debug", "info", "error"

        :param event_or_level: 事件类型或日志级别
        :return: 过滤后的结果列表

        Python 特殊语法：
        - .get(key): 字典方法获取值（类似于 Java 的 Map.get()）
        - is not None: 判断非 None（而不是简单的 if value）
        """
        res = []  # 结果列表

        # 遍历所有结果项
        # for r in self._data: 类似于 Java 的 for (Map<String, Object> r : data)
        for r in self._data:
            ev = r.get("event")  # 获取事件类型
            lv = r.get("level")  # 获取日志级别

            # 检查 event 是否匹配
            # is not None 确保字段存在且不为 None
            if ev is not None and ev == event_or_level:
                res.append(r)
            # 检查 level 是否匹配
            elif lv is not None and lv == event_or_level:
                res.append(r)

        return res
