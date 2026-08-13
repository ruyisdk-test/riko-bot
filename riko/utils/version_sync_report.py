#!/usr/bin/env python3
# riko/utils/version_sync_report.py - 版本同步 Markdown 报告生成
"""
版本同步 Markdown 报告生成工具

将 version-sync 的对比结果渲染成 Markdown 文档，以表格形式展示
每个上游镜像的版本变化（有变更 / 无变更 / 跳过）。

使用场景：
- version-sync --dry-run 生成报告
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Set

# 状态常量
STATUS_CHANGED = "有变更"
STATUS_UNCHANGED = "无变更"
STATUS_SKIPPED = "跳过"


@dataclass
class MirrorReportRow:
    """
    单个镜像（combo）的报告行

    属性:
        package_name: 上游包名（如：freebsd）
        combo_name: 镜像名称（如：freebsd-riscv64-mini-live）
            对于跳过的包，可以折叠为 "（全部 N 个镜像）" 等说明文字
        upstream_versions: 上游可用版本集合
        to_add: 待添加版本集合
        to_delete: 待删除版本集合
        status: 状态（有变更 / 无变更 / 跳过）
        skip_reason: 跳过原因（status 为跳过时使用）
    """
    package_name: str
    combo_name: str
    upstream_versions: Set[str] = field(default_factory=set)
    to_add: Set[str] = field(default_factory=set)
    to_delete: Set[str] = field(default_factory=set)
    status: str = STATUS_UNCHANGED
    skip_reason: str = ""


def _join_versions(versions: Set[str]) -> str:
    """
    将版本集合渲染为表格单元格内容

    :param versions: 版本集合
    :return: 逗号分隔的版本字符串；空集合返回 "—"
    """
    if not versions:
        return "—"
    return ", ".join(sorted(versions))


def _status_cell(row: MirrorReportRow) -> str:
    """
    渲染状态列

    跳过时附带原因，其余状态直接显示。
    """
    if row.status == STATUS_SKIPPED:
        if row.skip_reason:
            return f"跳过：{row.skip_reason}"
        return "跳过"
    return row.status


def generate_version_sync_markdown(
    rows: List[MirrorReportRow],
    generated_at: str = "",
    dry_run: bool = True,
    total_packages: int = 0,
    total_combos: int = 0,
) -> str:
    """
    生成版本同步 Markdown 报告

    :param rows: 所有镜像的报告行（含变更/无变更/跳过）
    :param generated_at: 生成时间字符串（默认取当前时间）
    :param dry_run: 是否为 dry-run 模式
    :param total_packages: 扫描的包总数
    :param total_combos: 扫描的镜像总数
    :return: Markdown 文本
    """
    if not generated_at:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 统计
    changed_rows = [r for r in rows if r.status == STATUS_CHANGED]
    unchanged_rows = [r for r in rows if r.status == STATUS_UNCHANGED]
    skipped_rows = [r for r in rows if r.status == STATUS_SKIPPED]

    total_to_add = sum(len(r.to_add) for r in changed_rows)
    total_to_delete = sum(len(r.to_delete) for r in changed_rows)

    mode = "dry-run（仅预览，不执行修改）" if dry_run else "实际执行"

    lines = [
        "# 版本同步报告",
        "",
        f"- 生成时间: {generated_at}",
        f"- 模式: {mode}",
        f"- 扫描包数: {total_packages}",
        f"- 镜像总数: {total_combos}",
        "",
        "## 变更汇总",
        "",
        "| 指标 | 数量 |",
        "|------|------|",
        f"| 有变更的镜像 | {len(changed_rows)} |",
        f"| 无变更的镜像 | {len(unchanged_rows)} |",
        f"| 跳过的包 | {len(skipped_rows)} |",
        f"| 待添加版本 | {total_to_add} |",
        f"| 待删除版本 | {total_to_delete} |",
        "",
        "## 各镜像变更明细",
        "",
        "| 上游包 | 镜像 | 上游版本 | 待添加版本 | 待删除版本 | 状态 |",
        "|--------|------|----------|-----------|-----------|------|",
    ]

    for row in rows:
        lines.append(
            f"| {row.package_name} | {row.combo_name} "
            f"| {_join_versions(row.upstream_versions)} "
            f"| {_join_versions(row.to_add)} "
            f"| {_join_versions(row.to_delete)} "
            f"| {_status_cell(row)} |"
        )

    lines.append("")
    return "\n".join(lines)


def write_version_sync_report(markdown: str, output_dir: Path, timestamp: str = "") -> Path:
    """
    将 Markdown 报告写入文件

    :param markdown: Markdown 文本
    :param output_dir: 输出目录
    :param timestamp: 时间戳（用于文件名，默认取当前时间）
    :return: 写入的报告文件路径
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_file = output_dir / f"version-sync-{timestamp}.md"
    report_file.write_text(markdown, encoding="utf-8")
    return report_file
