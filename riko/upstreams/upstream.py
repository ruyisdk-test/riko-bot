# -*- coding: utf-8 -*-
"""
上游源协议定义

该模块定义了上游源（Upstream）的协议接口，所有具体的上游源实现都需要遵循此协议。
"""

from typing import ClassVar, Protocol

class Upstream(Protocol):
    """
    上游源协议

    这是一个 Protocol 类，定义了所有上游源实现必须遵循的接口规范。
    使用 Protocol 可以实现结构化子类型，即只要某个类实现了 Protocol 中定义的所有属性和方法，
    就被视为该 Protocol 的子类型，无需显式继承。

    Attributes:
        source: 类变量，标识上游源的类别（如 "github"、"gitlab" 等）
    """

    source: ClassVar[str]  # 上游源的类型标识符
