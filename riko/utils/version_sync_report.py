#!/usr/bin/env python3

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Set

STATUS_CHANGED = "changed"
STATUS_UNCHANGED = "unchanged"
STATUS_SKIPPED = "skipped"


@dataclass
class MirrorReportRow:
    package_name: str
    combo_name: str
    upstream_versions: Set[str] = field(default_factory=set)
    to_add: Set[str] = field(default_factory=set)
    to_delete: Set[str] = field(default_factory=set)
    status: str = STATUS_UNCHANGED
    skip_reason: str = ""


def _join_versions(versions: Set[str]) -> str:
    if not versions:
        return "—"
    return ", ".join(sorted(versions))


def _status_cell(row: MirrorReportRow) -> str:
    if row.status == STATUS_SKIPPED:
        if row.skip_reason:
            return f"Skipped: {row.skip_reason}"
        return "Skipped"
    return row.status


def generate_version_sync_markdown(
    rows: List[MirrorReportRow],
    generated_at: str = "",
    dry_run: bool = True,
    total_packages: int = 0,
    total_combos: int = 0,
) -> str:
    if not generated_at:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    changed_rows = [r for r in rows if r.status == STATUS_CHANGED]
    unchanged_rows = [r for r in rows if r.status == STATUS_UNCHANGED]
    skipped_rows = [r for r in rows if r.status == STATUS_SKIPPED]

    total_to_add = sum(len(r.to_add) for r in changed_rows)
    total_to_delete = sum(len(r.to_delete) for r in changed_rows)

    mode = "dry-run (preview only, no changes applied)" if dry_run else "applied"

    lines = [
        "# Version Sync Report",
        "",
        f"- Generated at: {generated_at}",
        f"- Mode: {mode}",
        f"- Packages scanned: {total_packages}",
        f"- Total mirrors: {total_combos}",
        "",
        "## Change Summary",
        "",
        "| Metric | Count |",
        "|------|------|",
        f"| Mirrors with changes | {len(changed_rows)} |",
        f"| Mirrors unchanged | {len(unchanged_rows)} |",
        f"| Packages skipped | {len(skipped_rows)} |",
        f"| Versions to add | {total_to_add} |",
        f"| Versions to delete | {total_to_delete} |",
        "",
        "## Per-Mirror Changes",
        "",
        "| Upstream | Mirror | Upstream versions | To add | To delete | Status |",
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
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_file = output_dir / f"version-sync-{timestamp}.md"
    report_file.write_text(markdown, encoding="utf-8")
    return report_file
