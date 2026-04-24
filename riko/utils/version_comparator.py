#!/usr/bin/env python3
# riko/utils/version_comparator.py - 版本对比工具
"""
版本对比和差异计算工具

使用场景：
- 对比上游版本与仓库版本
- 计算需要添加和删除的版本
- 生成版本同步报告

"""

import logging
from dataclasses import dataclass
from typing import Set

logger = logging.getLogger(__name__)


@dataclass
class VersionDiff:
    """
    版本差异结果

    属性:
        package_name: 包名（如：freebsd）
        combo_name: combo 名称（如：freebsd-riscv64-mini-live）
        upstream_versions: 上游可用版本集合

        # 本地 cache 相关（实际要增删的）
        cache_versions: Set[str]
        cache_to_add: Set[str]      # 实际要添加
        cache_to_delete: Set[str]   # 实际要删除

        # 远程仓库相关（仅展示参考）
        remote_versions: Set[str]
        remote_to_add: Set[str]
        remote_to_delete: Set[str]

        has_changes: bool  # 基于 cache 判断
    """
    package_name: str
    combo_name: str
    upstream_versions: Set[str]

    # 本地 cache 相关
    cache_versions: Set[str]
    cache_to_add: Set[str]
    cache_to_delete: Set[str]

    # 远程仓库相关
    remote_versions: Set[str]
    remote_to_add: Set[str]
    remote_to_delete: Set[str]

    has_changes: bool

    # 兼容性别名（用于旧代码）
    @property
    def repo_versions(self) -> Set[str]:
        return self.cache_versions

    @property
    def to_add(self) -> Set[str]:
        return self.cache_to_add

    @property
    def to_delete(self) -> Set[str]:
        return self.cache_to_delete

    def summary(self) -> str:
        """
        生成差异摘要（基于 cache）

        :return: 差异摘要字符串

        示例输出:
            "freebsd-riscv64-mini-live: +1 versions, -2 versions"
        """
        parts = []
        if self.cache_to_add:
            parts.append(f"+{len(self.cache_to_add)} versions")
        if self.cache_to_delete:
            parts.append(f"-{len(self.cache_to_delete)} versions")

        if parts:
            return f"{self.combo_name}: {', '.join(parts)}"
        else:
            return f"{self.combo_name}: no changes"

    def detailed_summary(self) -> str:
        """
        生成详细差异报告（区分 cache 和 remote）

        :return: 详细报告字符串

        """
        lines = [
            f"Package: {self.package_name}",
            f"Combo: {self.combo_name}",
        ]

        # Cache 变更（实际要执行的）
        if self.cache_to_add or self.cache_to_delete:
            lines.append("\n[Local Cache] Actual changes to apply:")
            if self.cache_to_add:
                lines.append(f"  To Add: {', '.join(sorted(self.cache_to_add))}")
            if self.cache_to_delete:
                lines.append(f"  To Delete: {', '.join(sorted(self.cache_to_delete))}")
        else:
            lines.append("\n[Local Cache] No changes needed")

        # Remote 变更（仅展示参考）
        if self.remote_to_add or self.remote_to_delete:
            lines.append("\n[Remote Repo] Reference only (not applied):")
            if self.remote_to_add:
                lines.append(f"  To Add: {', '.join(sorted(self.remote_to_add))}")
            if self.remote_to_delete:
                lines.append(f"  To Delete: {', '.join(sorted(self.remote_to_delete))}")

        return '\n'.join(lines)


class VersionComparator:
    """
    版本对比工具

    1. 对比上游版本与仓库版本
    2. 计算需要添加和删除的版本
    3. 生成版本差异报告

    """

    def compare(
        self,
        package_name: str,
        combo_name: str,
        upstream_versions: Set[str],
        repo_versions: Set[str]
    ) -> VersionDiff:
        """
        对比版本差异

        逻辑:
            - to_delete = repo_versions - upstream_versions
            - to_add = upstream_versions - repo_versions
            - has_changes = bool(to_delete or to_add)

        """
        # 需要删除的版本：仓库有但上游没有
        to_delete = repo_versions - upstream_versions

        # 需要添加的版本：上游有但仓库没有
        to_add = upstream_versions - repo_versions

        has_changes = bool(to_delete or to_add)

        logger.debug(f"Compared versions for {combo_name}: "
                   f"upstream={len(upstream_versions)}, "
                   f"repo={len(repo_versions)}, "
                   f"to_add={len(to_add)}, "
                   f"to_delete={len(to_delete)}")

        return VersionDiff(
            package_name=package_name,
            combo_name=combo_name,
            upstream_versions=upstream_versions,
            cache_versions=repo_versions,
            cache_to_add=to_add,
            cache_to_delete=to_delete,
            remote_versions=set(),
            remote_to_add=set(),
            remote_to_delete=set(),
            has_changes=has_changes
        )

    def compare_with_mappings(
        self,
        package_name: str,
        combo_name: str,
        upstream_versions: Set[str],
        cache_versions_info: dict,
        remote_versions_info: dict = None
    ) -> VersionDiff:
        """
        使用版本映射信息对比版本差异

        同时计算：
        - cache vs upstream（实际要执行的变更）
        - remote vs upstream（仅展示参考）

        这个方法考虑了版本格式的差异，通过 manifest 文件中的 upstream_version
        字段来准确判断两个版本是否相同。

        :param cache_versions_info: 本地 cache 版本信息（实际变更）
        :param remote_versions_info: 远程仓库版本信息（仅参考）
        """
        if remote_versions_info is None:
            remote_versions_info = cache_versions_info

        # 计算 cache 变更
        cache_to_add, cache_to_delete = self._compute_diff(
            upstream_versions, cache_versions_info
        )

        # 计算 remote 变更（仅参考）
        remote_to_add, remote_to_delete = self._compute_diff(
            upstream_versions, remote_versions_info
        )

        cache_file_versions = cache_versions_info.get("file_versions", set())
        remote_file_versions = remote_versions_info.get("file_versions", set())

        has_changes = bool(cache_to_delete or cache_to_add)

        logger.debug(f"Compared versions for {combo_name}: "
                   f"upstream={len(upstream_versions)}, "
                   f"cache_files={len(cache_file_versions)}, "
                   f"remote_files={len(remote_file_versions)}, "
                   f"cache_to_add={len(cache_to_add)}, "
                   f"cache_to_delete={len(cache_to_delete)}, "
                   f"remote_to_add={len(remote_to_add)}, "
                   f"remote_to_delete={len(remote_to_delete)}")

        return VersionDiff(
            package_name=package_name,
            combo_name=combo_name,
            upstream_versions=upstream_versions,
            cache_versions=cache_file_versions,
            cache_to_add=cache_to_add,
            cache_to_delete=cache_to_delete,
            remote_versions=remote_file_versions,
            remote_to_add=remote_to_add,
            remote_to_delete=remote_to_delete,
            has_changes=has_changes
        )

    def _compute_diff(
        self,
        upstream_versions: Set[str],
        versions_info: dict
    ) -> tuple:
        """
        计算版本差异的内部方法

        :return: (to_add, to_delete) 元组
        """
        file_versions = versions_info.get("file_versions", set())
        upstream_in_file_versions = versions_info.get("upstream_versions", set())
        mapping = versions_info.get("mapping", {})

        # 需要添加的版本：上游有但仓库没有的（通过 upstream_version 判断）
        to_add = upstream_versions - upstream_in_file_versions

        # 需要删除的版本：仓库有但上游没有的（检查 upstream_version）
        to_delete = set()
        for file_version, upstream_version in mapping.items():
            if upstream_version not in upstream_versions:
                to_delete.add(file_version)
                logger.debug(f"Version {file_version} (upstream: {upstream_version}) not in upstream, marking for deletion")

        # 对于没有 upstream_version 映射的文件版本，使用直接比较
        file_versions_without_mapping = file_versions - set(mapping.keys())
        for file_version in file_versions_without_mapping:
            if file_version not in upstream_versions:
                to_delete.add(file_version)
                logger.debug(f"Version {file_version} (no upstream mapping) not in upstream, marking for deletion")

        return to_add, to_delete

    @staticmethod
    def parse_version_from_filename(filename: str) -> str:
        """
        从 manifest 文件名提取版本号

        :param filename: 文件名（如：14.0.0.toml）
        :return: 版本号（如：14.0.0）

        支持的格式：
            - "X.Y.Z.toml" -> "X.Y.Z"
            - "X.Y.Z" -> "X.Y.Z"
            - "X.Y.toml" -> "X.Y"

        """
        # 去除 .toml 后缀
        if filename.endswith('.toml'):
            return filename[:-5]
        return filename

    @staticmethod
    def normalize_version(version: str) -> str:
        """
        标准化版本号格式

        处理逻辑：
        1. 去除 v 前缀（如：v1.0 -> 1.0）
        2. 统一为三段格式（如：1.0 -> 1.0.0）
        3. 去除多余的前后缀

        :param version: 原始版本号
        :return: 标准化后的版本号

        """
        if not version:
            return "0.0.0"

        # 去除 v 前缀
        normalized = version.lstrip('vV')

        # 分割版本号
        parts = normalized.split('.')

        # 补足到三段（如：1.0 -> 1.0.0）
        while len(parts) < 3:
            parts.append('0')

        # 限制为三段
        parts = parts[:3]

        return '.'.join(parts)
