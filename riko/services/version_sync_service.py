#!/usr/bin/env python3

import argparse
import logging
import tomllib
from datetime import datetime
from typing import Dict, List, Set, Any

import git

from .manifest_service import ManifestService
from .pr_service import PRService
from ..config.const import basedir, dry_run_docs_dir, riko_manifests_dir, ruyi_pkgs_dir
from ..database import get_recorder
from ..database import record_command
from ..upstreams.version_fetcher import VersionFetcher
from ..utils.version_comparator import VersionComparator, VersionDiff
from ..utils.version_sync_report import (
    MirrorReportRow,
    STATUS_CHANGED,
    STATUS_SKIPPED,
    STATUS_UNCHANGED,
    generate_version_sync_markdown,
    write_version_sync_report,
)

logger = logging.getLogger(__name__)


class VersionSyncService:
    PACKAGES_INDEX_ROOT = basedir.parent / "packages-index"
    MANIFESTS_ROOT = PACKAGES_INDEX_ROOT / "packages" / "board-image"
    DEFAULT_REPO_OWNER = "SmulllLu"
    DEFAULT_REPO_NAME = "packages-index"
    DEFAULT_BASE_BRANCH = "pr"
    DEFAULT_BRANCH_PREFIX = "manifest-update"

    @staticmethod
    def scan_all_packages() -> Dict[str, Any]:
        packages = {}

        board_image_dir = ruyi_pkgs_dir / "board-image"
        if not board_image_dir.exists():
            logger.warning(f"Board-image directory not found: {board_image_dir}")
            return packages

        for pkg_dir in board_image_dir.iterdir():
            if not pkg_dir.is_dir():
                continue

            riko_toml = pkg_dir / "riko.toml"
            if not riko_toml.exists():
                continue

            try:
                with open(riko_toml, "rb") as f:
                    config = tomllib.load(f)
                nvchecker = config.get("nvchecker", {})
                entities = config.get("entities", {})

                package_name = pkg_dir.name
                packages[package_name] = {
                    "nvchecker": nvchecker,
                    "combos": entities.get("image-combo", []),
                    "riko_toml": config  # keep full config for manifest generation
                }

                logger.debug(f"Scanned package: {package_name}, combos: {packages[package_name]['combos']}")

            except Exception as e:
                logger.warning(f"Failed to parse {riko_toml}: {e}")

        return packages

    @staticmethod
    def get_repo_versions(combo_name: str, include_upstream_versions: bool = True) -> Set[str]:
        info = VersionSyncService.get_repo_versions_info(combo_name)
        versions = info["file_versions"].copy()

        if include_upstream_versions:
            versions.update(info["upstream_versions"])

        logger.debug(f"Found {len(versions)} versions for {combo_name}: {versions}")
        return versions

    @staticmethod
    def get_repo_versions_info(combo_name: str) -> dict:
        import tomllib

        info = {
            "file_versions": set(),
            "upstream_versions": set(),
            "mapping": {}  # file_version -> upstream_version
        }

        combo_dir = VersionSyncService.MANIFESTS_ROOT / combo_name

        if not combo_dir.exists():
            logger.debug(f"Combo directory not found: {combo_name}")
            return info

        for manifest_file in combo_dir.glob("*.toml"):
            file_version = VersionComparator.parse_version_from_filename(manifest_file.name)
            info["file_versions"].add(file_version)

            try:
                with open(manifest_file, "rb") as f:
                    manifest_data = tomllib.load(f)
                    upstream_version = manifest_data.get("metadata", {}).get("upstream_version")
                    if upstream_version:
                        info["upstream_versions"].add(upstream_version)
                        info["mapping"][file_version] = upstream_version
                        logger.debug(f"Mapping: {file_version} -> {upstream_version}")
            except Exception as e:
                logger.debug(f"Failed to read manifest file {manifest_file}: {e}")

        logger.debug(f"Found {len(info['file_versions'])} file versions, "
                   f"{len(info['upstream_versions'])} upstream versions for {combo_name}")
        return info

    @staticmethod
    def get_cache_versions_info(combo_name: str) -> dict:
        import tomllib

        info = {
            "file_versions": set(),
            "upstream_versions": set(),
            "mapping": {}  # file_version -> upstream_version
        }

        combo_dir = riko_manifests_dir / "board-image" / combo_name

        if not combo_dir.exists():
            logger.debug(f"Cache combo directory not found: {combo_dir}")
            return info

        for manifest_file in combo_dir.glob("*.toml"):
            file_version = VersionComparator.parse_version_from_filename(manifest_file.name)
            info["file_versions"].add(file_version)

            try:
                with open(manifest_file, "rb") as f:
                    manifest_data = tomllib.load(f)
                    upstream_version = manifest_data.get("metadata", {}).get("upstream_version")
                    if upstream_version:
                        info["upstream_versions"].add(upstream_version)
                        info["mapping"][file_version] = upstream_version
                        logger.debug(f"Cache mapping: {file_version} -> {upstream_version}")
            except Exception as e:
                logger.debug(f"Failed to read cache manifest file {manifest_file}: {e}")

        logger.debug(f"Found {len(info['file_versions'])} cache file versions, "
                   f"{len(info['upstream_versions'])} cache upstream versions for {combo_name}")
        return info

    @staticmethod
    @record_command("version-sync")
    def sync_all(args: argparse.Namespace) -> None:
        recorder = get_recorder()
        dry_run = getattr(args, 'dry_run', False)

        logger.info("=" * 70)
        logger.info("Starting version sync...")
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        logger.info("=" * 70)

        packages = VersionSyncService.scan_all_packages()
        logger.info(f"Found {len(packages)} packages to scan")

        if not packages:
            logger.warning("No packages found to sync")
            return

        all_diffs = []

        # Report rows for the Markdown report (changed/unchanged/skipped)
        report_rows: List[MirrorReportRow] = []
        total_combos = 0

        for package_name, package_info in packages.items():
            nvchecker = package_info["nvchecker"]
            combos = package_info["combos"]

            if not nvchecker:
                logger.warning(f"No nvchecker config for {package_name}")
                report_rows.append(MirrorReportRow(
                    package_name=package_name,
                    combo_name="(no nvchecker config)",
                    status=STATUS_SKIPPED,
                    skip_reason="no nvchecker config",
                ))
                continue

            if not combos:
                logger.warning(f"No combos defined for {package_name}")
                report_rows.append(MirrorReportRow(
                    package_name=package_name,
                    combo_name="(no image defined)",
                    status=STATUS_SKIPPED,
                    skip_reason="no image-combo defined",
                ))
                continue

            fetcher = VersionFetcher.from_nvchecker(nvchecker)

            upstream_versions = fetcher.fetch_all_versions()
            logger.info(f"{package_name} upstream versions: {upstream_versions}")

            if not upstream_versions:
                logger.warning(f"Skipping {package_name}: no upstream versions found (possible network error)")
                report_rows.append(MirrorReportRow(
                    package_name=package_name,
                    combo_name=f"(all {len(combos)} images)",
                    status=STATUS_SKIPPED,
                    skip_reason="failed to fetch upstream versions (possible network error)",
                ))
                continue

            for combo_name in combos:
                total_combos += 1

                # Cache is what actually changes; remote is reference-only
                cache_versions_info = VersionSyncService.get_cache_versions_info(combo_name)

                remote_versions_info = VersionSyncService.get_repo_versions_info(combo_name)

                comparator = VersionComparator()
                diff = comparator.compare_with_mappings(
                    package_name=package_name,
                    combo_name=combo_name,
                    upstream_versions=upstream_versions,
                    cache_versions_info=cache_versions_info,
                    remote_versions_info=remote_versions_info
                )

                if diff.has_changes:
                    all_diffs.append(diff)
                    report_rows.append(MirrorReportRow(
                        package_name=package_name,
                        combo_name=combo_name,
                        upstream_versions=upstream_versions,
                        to_add=diff.cache_to_add,
                        to_delete=diff.cache_to_delete,
                        status=STATUS_CHANGED,
                    ))
                    logger.info(f"✓ {diff.summary()}")

                    if args.verbose:
                        logger.info("\n" + diff.detailed_summary() + "\n")
                else:
                    report_rows.append(MirrorReportRow(
                        package_name=package_name,
                        combo_name=combo_name,
                        upstream_versions=upstream_versions,
                        status=STATUS_UNCHANGED,
                    ))

        logger.info("=" * 70)
        logger.info("VERSION SYNC SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total packages scanned: {len(packages)}")
        logger.info(f"Total combos with changes: {len(all_diffs)}")

        if all_diffs:
            # Stats are based on the local cache
            total_cache_to_add = sum(len(d.cache_to_add) for d in all_diffs)
            total_cache_to_delete = sum(len(d.cache_to_delete) for d in all_diffs)

            has_remote_info = any(len(d.remote_versions) > 0 for d in all_diffs)

            logger.info("")
            logger.info("-" * 70)
            logger.info("FINAL CHANGES (local cache vs upstream)")
            logger.info("-" * 70)
            logger.info(f"  Versions to ADD:    {total_cache_to_add}")
            logger.info(f"  Versions to DELETE: {total_cache_to_delete}")
            logger.info("")

            logger.info("Details:")
            for diff in all_diffs:
                parts = []
                if diff.cache_to_add:
                    parts.append(f"+{len(diff.cache_to_add)}")
                if diff.cache_to_delete:
                    parts.append(f"-{len(diff.cache_to_delete)}")
                action = ", ".join(parts) if parts else "no changes"
                logger.info(f"  [{action}] {diff.combo_name}")

            # Remote info is reference-only
            if has_remote_info:
                total_remote_to_add = sum(len(d.remote_to_add) for d in all_diffs)
                total_remote_to_delete = sum(len(d.remote_to_delete) for d in all_diffs)

                logger.info("")
                logger.info("-" * 70)
                logger.info("REFERENCE ONLY (remote repo vs upstream)")
                logger.info("-" * 70)
                logger.info(f"  Would add:    {total_remote_to_add}")
                logger.info(f"  Would delete: {total_remote_to_delete}")

                cache_only = total_cache_to_add - total_remote_to_add
                remote_only = total_remote_to_add - total_cache_to_add
                if cache_only != 0 or remote_only != 0:
                    logger.info("")
                    logger.info("  Difference from remote:")
                    if cache_only > 0:
                        logger.info(f"    Cache has {cache_only} more versions to add than remote")
                    if remote_only > 0:
                        logger.info(f"    Remote has {remote_only} more versions to add than cache")
            else:
                logger.info("")
                logger.info("-" * 70)
                logger.info("NOTE: Remote repo (packages-index) not found or empty")
                logger.info("      Showing only local cache vs upstream comparison")
                logger.info("-" * 70)

        if dry_run:
            # Generate a Markdown report paired with the .log file
            markdown = generate_version_sync_markdown(
                rows=report_rows,
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                dry_run=True,
                total_packages=len(packages),
                total_combos=total_combos,
            )

            report_dir = getattr(args, 'dry_run_report_dir', None) or dry_run_docs_dir
            report_timestamp = getattr(args, 'dry_run_timestamp', "")
            report_file = write_version_sync_report(markdown, report_dir, report_timestamp)
            logger.info(f"Dry-run report saved to: {report_file}")

            logger.info("\nDry run completed. No changes were made.")
            logger.info("Run without --dry-run to apply changes.")
            return

        if not all_diffs:
            logger.info("\nNo changes to apply.")
            return

        logger.info("\nStarting Git operations...")

        try:
            VersionSyncService._execute_git_operations(all_diffs, packages, recorder, args)
        except Exception as e:
            logger.error(f"Git operations failed: {e}")
            raise

        logger.info("=" * 70)
        logger.info("Version sync completed")
        logger.info("=" * 70)

    @staticmethod
    def _execute_git_operations(diffs: List[VersionDiff], packages: Dict[str, Any], recorder, args) -> None:
        from ..config.settings import settings
        import subprocess

        # CLI args take precedence over config
        gh_token = args.github_token or settings.github_token
        repo_owner = args.repo_owner or settings.github_repo_owner or VersionSyncService.DEFAULT_REPO_OWNER
        repo_name = args.repo_name or settings.github_repo_name or VersionSyncService.DEFAULT_REPO_NAME
        base_branch = args.base_branch or settings.github_base_branch or VersionSyncService.DEFAULT_BASE_BRANCH
        branch_prefix = args.branch_prefix or settings.pr_branch_prefix or VersionSyncService.DEFAULT_BRANCH_PREFIX

        if not VersionSyncService.PACKAGES_INDEX_ROOT.exists():
            recorder.record_pr_creation(
                package_name="version-sync",
                version="",
                status="failed",
                error_type="FileNotFoundError",
                error_message=f"packages-index repository not found: {VersionSyncService.PACKAGES_INDEX_ROOT}"
            )
            raise FileNotFoundError(f"packages-index repository not found")

        try:
            repo = git.Repo(VersionSyncService.PACKAGES_INDEX_ROOT)

            try:
                repo.git.clean("-fd", "-d")
                logger.info("Cleaned untracked files in packages-index")
            except git.GitError as e:
                logger.warning(f"Failed to clean untracked files: {e}")

            logger.info(f"Checking out base branch: {base_branch}")
            try:
                repo.git.checkout(base_branch)
                # --ff-only fails on divergent local/remote branches
                repo.git.pull("origin", base_branch, ff_only=True)
            except git.GitError as e:
                logger.error(f"Failed to checkout base branch: {e}")
                recorder.record_pr_creation(
                    package_name="version-sync",
                    version="",
                    status="failed",
                    error_type="GitCommandError",
                    error_message=f"Failed to checkout base branch: {e}"
                )
                raise

            # One feature branch for all changes
            feature_branch = f"{branch_prefix}-all-boards-{base_branch}"
            logger.info(f"Using feature branch: {feature_branch}")

            if feature_branch in [ref.name for ref in repo.refs]:
                try:
                    repo.git.checkout(feature_branch)
                    logger.info(f"Checked out existing branch: {feature_branch}")
                except git.GitError as e:
                    logger.warning(f"Failed to checkout branch: {e}")

                try:
                    repo.git.rebase(f"origin/{base_branch}")
                except git.GitError:
                    pass
            else:
                try:
                    repo.git.checkout("-b", feature_branch, f"origin/{base_branch}")
                    logger.info(f"Created new branch: {feature_branch}")
                except git.GitError as e:
                    logger.error(f"Failed to create branch: {e}")
                    raise

            files_to_delete = []
            files_to_add = []

            # ManifestService.generate() generates for all combos of a package
            package_versions_to_add: Dict[str, Set[str]] = {}
            for diff in diffs:
                if diff.to_delete:
                    for version in diff.to_delete:
                        manifest_file = VersionSyncService.MANIFESTS_ROOT / diff.combo_name / f"{version}.toml"
                        if manifest_file.exists():
                            files_to_delete.append(str(manifest_file))

                if diff.to_add:
                    if diff.package_name not in package_versions_to_add:
                        package_versions_to_add[diff.package_name] = set()
                    package_versions_to_add[diff.package_name].update(diff.to_add)

            for package_name, versions_to_add in package_versions_to_add.items():
                logger.info(f"Generating manifests for {package_name}, versions: {sorted(versions_to_add)}")
                try:
                    ManifestService.generate(
                        up_name=package_name,
                        gen_vers=list(versions_to_add),
                        down_grade=False
                    )

                    riko_toml = packages[package_name].get("riko_toml", {})
                    combos = riko_toml.get("entities", {}).get("image-combo", [])
                    for combo_name in combos:
                        for version in versions_to_add:
                            combo_dir = riko_manifests_dir / "board-image" / combo_name
                            if not combo_dir.exists():
                                logger.warning(f"Combo directory not found: {combo_dir}")
                                continue

                            # Filename may carry a version prefix like 0.20240720.0.toml
                            manifest_files = list(combo_dir.glob(f"*{version}*.toml"))

                            if not manifest_files:
                                logger.warning(f"Manifest file not found for {combo_name} version {version}")
                                continue

                            # Use the latest file if multiple match
                            manifest_file = max(manifest_files, key=lambda p: p.stat().st_mtime)
                            logger.debug(f"Found manifest file: {manifest_file}")

                            target_dir = VersionSyncService.MANIFESTS_ROOT / combo_name
                            target_file = target_dir / manifest_file.name  # keep original filename
                            target_dir.mkdir(parents=True, exist_ok=True)
                            import shutil
                            shutil.copy2(manifest_file, target_file)
                            files_to_add.append(str(target_file))
                            logger.info(f"✓ Generated manifest: {target_file}")

                except Exception as e:
                    logger.error(f"✗ Failed to generate manifests for {package_name}: {e}")
                    recorder.record_pr_creation(
                        package_name=package_name,
                        version=",".join(sorted(versions_to_add)),
                        status="failed",
                        error_type=type(e).__name__,
                        error_message=str(e)
                    )

            if files_to_delete:
                logger.info(f"Deleting {len(files_to_delete)} files...")
                try:
                    repo.index.remove(files_to_delete)
                    for f in files_to_delete:
                        try:
                            subprocess.run(["rm", "-f", f], check=True)
                            logger.debug(f"Deleted: {f}")
                        except subprocess.CalledProcessError as e:
                            logger.warning(f"Failed to delete {f}: {e}")
                except git.GitError as e:
                    logger.error(f"Failed to remove files from index: {e}")

            if files_to_add:
                logger.info(f"Adding {len(files_to_add)} new files to git...")
                try:
                    repo.index.add(files_to_add)
                    logger.info("Added new files to git index")
                except git.GitError as e:
                    logger.error(f"Failed to add files to index: {e}")

            if files_to_delete or files_to_add:
                commit_msg_parts = []
                for diff in diffs:
                    if diff.to_delete:
                        commit_msg_parts.append(f"remove {len(diff.to_delete)} old versions")
                    if diff.to_add:
                        commit_msg_parts.append(f"add {len(diff.to_add)} new versions")

                if commit_msg_parts:
                    commit_msg = "version-sync: " + ", ".join(commit_msg_parts)
                    logger.info(f"Committing: {commit_msg}")

                    try:
                        repo.index.commit(commit_msg)
                        logger.info("Commit successful")
                    except git.GitError as e:
                        logger.error(f"Failed to commit: {e}")
                        raise
            else:
                logger.info("No file changes to commit")
                commit_msg = None

            if commit_msg:
                logger.info(f"Pushing branch to {repo_owner}/{repo_name}...")
                origin = repo.remote(name="origin")
                remote_url = origin.url

                # Authenticate by embedding the token in the URL
                if remote_url.startswith("https://") and gh_token:
                    token_url = f"https://{gh_token}@github.com/{repo_owner}/{repo_name}.git"
                    origin.set_url(token_url)

                try:
                    repo.git.push("origin", feature_branch)
                    logger.info(f"Pushed: {feature_branch} -> origin/{feature_branch}")
                except git.GitError as e:
                    logger.error(f"Failed to push: {e}")
                    raise
                finally:
                    # Restore the original URL to avoid leaking the token
                    if remote_url.startswith("https://") and gh_token:
                        origin.set_url(remote_url)

                logger.info("✓ Git operations completed successfully")

                total_to_add = sum(len(d.to_add) for d in diffs)
                total_to_delete = sum(len(d.to_delete) for d in diffs)

                package_names = set(d.package_name for d in diffs)
                pr_title = f"manifests: update all board-image manifests ({len(package_names)} packages, {total_to_add} add, {total_to_delete} remove)"

                pr_body_parts = [
                    "## Summary",
                    "",
                    "This PR updates all board-image manifests based on upstream versions.",
                    "Generated by version-sync tool from ruyi-packaging repository.",
                    "",
                    "## Changes",
                    "",
                ]

                package_stats: Dict[str, Dict[str, int]] = {}
                for diff in diffs:
                    pkg = diff.package_name
                    if pkg not in package_stats:
                        package_stats[pkg] = {"add": 0, "remove": 0}
                    package_stats[pkg]["add"] += len(diff.to_add)
                    package_stats[pkg]["remove"] += len(diff.to_delete)

                for pkg, stats in sorted(package_stats.items()):
                    parts = []
                    if stats["add"] > 0:
                        parts.append(f"add {stats['add']} versions")
                    if stats["remove"] > 0:
                        parts.append(f"remove {stats['remove']} versions")
                    pr_body_parts.append(f"- **{pkg}**: {', '.join(parts)}")

                pr_body_parts.extend([
                    "",
                    "## Statistics",
                    "",
                    f"- Total packages: {len(package_names)}",
                    f"- Total files changed: {total_to_add + total_to_delete}",
                    f"- Versions to add: {total_to_add}",
                    f"- Versions to remove: {total_to_delete}",
                    "",
                    "---",
                    "🤖 Generated with version-sync tool",
                ])
                pr_body = "\n".join(pr_body_parts)

                PRService._create_github_pr(
                    gh_token=gh_token,
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    base_branch=base_branch,
                    feature_branch=feature_branch,
                    title=pr_title,
                    body=pr_body,
                    recorder=recorder,
                    package_name="version-sync",
                    version=",".join([f"{d.package_name}:{','.join(d.to_add)}" for d in diffs])
                )

        except Exception as e:
            logger.error(f"Git operations failed: {e}")
            raise