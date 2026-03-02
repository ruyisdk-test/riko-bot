"""
Riko API - 核心数据模型定义

本模块定义了 Ruko 项目的核心数据模型，用于表示和管理包的完整信息。
"""

import semver

from typing import Dict, Tuple, Union

from ..packages_index.manifests import PackageVersion
from ..upstreams.github import GithubUpstream
from ..upstreams.regex import RegexUpstream

# 导出公共 API
__all__ = ("GithubUpstream", "RegexUpstream", "RikoPkg")

# 上游源类型别名：支持 GitHub 或正则表达式
_UpstreamLike = Union[GithubUpstream, RegexUpstream]


class RikoPkg(PackageVersion):
    """
    Riko 包数据模型

    这是 Riko 项目的核心数据模型，继承自 PackageVersion，用于表示一个包的完整信息。
    包含包的分类、组合名、版本号、上游源和清单数据。
    """

    def __init__(self, category: str, combo: str, up_name: str,
                 version: semver.Version, upstream_version: str,
                 upstream: _UpstreamLike = None) -> None:
        # 初始化 RikoPkg 对象
        # 调用父类初始化，传递版本和空策略列表
        super().__init__(version, upstream_version, {})

        # 包的基本信息
        self._category: str = category        # 包分类
        self._combo: str = combo             # 包组合名
        self._upstream_name: str = up_name    # 上游包名

        # 上游源对象（用于获取 Release 信息等）
        self._upstream: _UpstreamLike = upstream

        # 清单就绪状态：控制是否可以写入文件
        self._manifest_ready: bool = False

    def set_manifest(self, manifest: Dict) -> None:
        """
        调用父类方法设置清单的完整内容，包括 metadata、distfiles、
        provisionable 等所有字段。
        """
        super().set_manifest(manifest)

    def set_manifest_ready(self) -> None:
        """
        标记清单为就绪状态

        清单就绪意味着清单已经完全生成并验证通过，可以写入文件。
        这通常在清单生成、推理规则、验证都成功完成后调用。
        """
        self._manifest_ready = True

    def set_manifest_not_ready(self) -> None:
        """
        标记清单为未就绪状态

        清单未就绪意味着清单不应该被写入文件，通常是因为：
        - 清单生成失败
        - 清单验证失败
        - keep_back 策略判断不需要更新

        使用场景：
            - manifests 命令中清单生成或验证失败时
            - keep_back 策略检查发现新旧版本相同时
        """
        self._manifest_ready = False

    def get_manifest_ready(self) -> bool:
        """
        获取清单就绪状态

        :return: True 表示清单就绪可以写入，False 表示未就绪
        """
        return self._manifest_ready

    def get_category(self) -> str:
        """
        获取包分类

        :return: 分类名称（如：board-image）

        使用场景：
            - 构建清单文件路径：riko_manifests_dir / category / combo
            - 日志记录：logger.info(f"Processing category: {pkg.get_category()}")
        """
        return self._category

    def get_combo(self) -> str:
        """
        获取包组合名

        combo 是一个特定的标识符，用于区分同一包的不同变体或配置。
        例如：openwrt-sifive-unmatched 是 openwrt-sifiveu 包的一个 combo。

        :return: 组合名称（如：openwrt-sifive-unmatched）

        使用场景：
            - 构建清单文件路径：riko_manifests_dir / category / combo
            - 日志记录：logger.info(f"Processing combo: {pkg.get_combo()}")
        """
        return self._combo

    def get_manifest(self) -> Tuple[Dict, bool]:
        """
        获取清单数据和就绪状态

        :return: (manifest_dict, is_ready) 元组
            - manifest_dict: 清单字典数据
            - is_ready: 清单是否就绪

        使用示例：
        """
        return super().get_manifest(), self._manifest_ready

    def get_version(self) -> semver.Version:
        """
        获取语义化版本对象

        :return: semver.Version 对象，可用于版本比较和操作

        使用示例：
        """
        return super().get_version()

    def get_upstream_version(self) -> str:
        """
        获取上游版本字符串

        :return: 版本字符串（如："0.2410.5"）

        使用场景：
            - 在清单 metadata 中设置 upstream_version 字段
            - 日志记录：logger.info(f"Upstream version: {pkg.get_upstream_version()}")
        """
        return super().get_upstream_version()

    def get_upstream(self) -> _UpstreamLike | None:
        """
        获取上游源对象

        上游源对象用于：
        - 获取 Release 资源信息（文件名、URL）
        - 执行正则匹配
        - 提取子字符串等

        :return: GithubUpstream 或 RegexUpstream 对象，如果没有则返回 None

        使用示例：
        """
        return self._upstream

    def get_upstream_name(self) -> str:
        """
        获取上游包名

        :return: 上游包名（如：openwrt-sifiveu）

        使用场景：
            - 日志记录：logger.info(f"Processing upstream: {pkg.get_upstream_name()}")
            - 构建文件名：f"{upstream_name}-{version}.toml"
        """
        return self._upstream_name
