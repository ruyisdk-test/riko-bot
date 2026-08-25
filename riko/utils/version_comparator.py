#!/usr/bin/env python3

import logging
from dataclasses import dataclass
from typing import Set

logger = logging.getLogger(__name__)


@dataclass
class VersionDiff:
    package_name: str
    combo_name: str
    upstream_versions: Set[str]

    cache_versions: Set[str]
    cache_to_add: Set[str]
    cache_to_delete: Set[str]

    remote_versions: Set[str]
    remote_to_add: Set[str]
    remote_to_delete: Set[str]

    has_changes: bool

    # backward-compat aliases
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
        lines = [
            f"Package: {self.package_name}",
            f"Combo: {self.combo_name}",
        ]

        if self.cache_to_add or self.cache_to_delete:
            lines.append("\n[Local Cache] Actual changes to apply:")
            if self.cache_to_add:
                lines.append(f"  To Add: {', '.join(sorted(self.cache_to_add))}")
            if self.cache_to_delete:
                lines.append(f"  To Delete: {', '.join(sorted(self.cache_to_delete))}")
        else:
            lines.append("\n[Local Cache] No changes needed")

        if self.remote_to_add or self.remote_to_delete:
            lines.append("\n[Remote Repo] Reference only (not applied):")
            if self.remote_to_add:
                lines.append(f"  To Add: {', '.join(sorted(self.remote_to_add))}")
            if self.remote_to_delete:
                lines.append(f"  To Delete: {', '.join(sorted(self.remote_to_delete))}")

        return '\n'.join(lines)


class VersionComparator:

    def compare(
        self,
        package_name: str,
        combo_name: str,
        upstream_versions: Set[str],
        repo_versions: Set[str]
    ) -> VersionDiff:
        to_delete = repo_versions - upstream_versions

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
        if remote_versions_info is None:
            remote_versions_info = cache_versions_info

        cache_to_add, cache_to_delete = self._compute_diff(
            upstream_versions, cache_versions_info
        )

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
        file_versions = versions_info.get("file_versions", set())
        upstream_in_file_versions = versions_info.get("upstream_versions", set())
        mapping = versions_info.get("mapping", {})

        to_add = upstream_versions - upstream_in_file_versions

        to_delete = set()
        for file_version, upstream_version in mapping.items():
            if upstream_version not in upstream_versions:
                to_delete.add(file_version)
                logger.debug(f"Version {file_version} (upstream: {upstream_version}) not in upstream, marking for deletion")

        # fall back to direct comparison for file versions without upstream mapping
        file_versions_without_mapping = file_versions - set(mapping.keys())
        for file_version in file_versions_without_mapping:
            if file_version not in upstream_versions:
                to_delete.add(file_version)
                logger.debug(f"Version {file_version} (no upstream mapping) not in upstream, marking for deletion")

        return to_add, to_delete

    @staticmethod
    def parse_version_from_filename(filename: str) -> str:
        if filename.endswith('.toml'):
            return filename[:-5]
        return filename

    @staticmethod
    def normalize_version(version: str) -> str:
        if not version:
            return "0.0.0"

        normalized = version.lstrip('vV')

        parts = normalized.split('.')

        while len(parts) < 3:
            parts.append('0')

        parts = parts[:3]

        return '.'.join(parts)
