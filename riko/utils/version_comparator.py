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
        repo_versions: 仓库已有版本集合
        to_delete: 需要删除的版本（仓库有但上游没有）
        to_add: 需要添加的版本（上游有但仓库没有）
        has_changes: 是否有变更
    """
    package_name: str
    combo_name: str
    upstream_versions: Set[str]
    repo_versions: Set[str]
    to_delete: Set[str]
    to_add: Set[str]
    has_changes: bool

    def summary(self) -> str:
        """
        生成差异摘要

        :return: 差异摘要字符串

        示例输出:
            "freebsd-riscv64-mini-live: +1 versions, -2 versions"
        """
        parts = []
        if self.to_add:
            parts.append(f"+{len(self.to_add)} versions")
        if self.to_delete:
            parts.append(f"-{len(self.to_delete)} versions")

        if parts:
            return f"{self.combo_name}: {', '.join(parts)}"
        else:
            return f"{self.combo_name}: no changes"

    def detailed_summary(self) -> str:
        """
        生成详细差异报告

        :return: 详细报告字符串

        """
        lines = [
            f"Package: {self.package_name}",
            f"Combo: {self.combo_name}",
        ]

        if self.to_add:
            lines.append(f"To Add: {', '.join(sorted(self.to_add))}")
        if self.to_delete:
            lines.append(f"To Delete: {', '.join(sorted(self.to_delete))}")

        if not self.to_add and not self.to_delete:
            lines.append("No changes needed")

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
            repo_versions=repo_versions,
            to_delete=to_delete,
            to_add=to_add,
            has_changes=has_changes
        )

    def compare_with_mappings(
        self,
        package_name: str,
        combo_name: str,
        upstream_versions: Set[str],
        repo_versions_info: dict
    ) -> VersionDiff:
        """
        使用版本映射信息对比版本差异

        这个方法考虑了版本格式的差异，通过 manifest 文件中的 upstream_version
        字段来准确判断两个版本是否相同。

        """
        file_versions = repo_versions_info.get("file_versions", set())
        repo_upstream_versions = repo_versions_info.get("upstream_versions", set())
        mapping = repo_versions_info.get("mapping", {})

        # 需要添加的版本：上游有但仓库没有的（通过 upstream_version 判断）
        to_add = upstream_versions - repo_upstream_versions

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

        has_changes = bool(to_delete or to_add)

        logger.debug(f"Compared versions for {combo_name}: "
                   f"upstream={len(upstream_versions)}, "
                   f"repo_files={len(file_versions)}, "
                   f"repo_upstream={len(repo_upstream_versions)}, "
                   f"to_add={len(to_add)}, "
                   f"to_delete={len(to_delete)}")

        return VersionDiff(
            package_name=package_name,
            combo_name=combo_name,
            upstream_versions=upstream_versions,
            repo_versions=file_versions,  # 使用文件名版本作为 repo_versions
            to_delete=to_delete,
            to_add=to_add,
            has_changes=has_changes
        )

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
