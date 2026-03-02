#!/usr/bin/env python3
# riko/services/version_sync_service.py - 版本同步服务
"""
版本同步服务

功能：
1. 扫描所有 board-image 包
2. 获取上游可用版本
3. 对比仓库已有版本
4. 执行 Git 操作（删除、添加）
5. 创建 PR 同步变更
"""

import argparse
import logging
import tomllib
from typing import Dict, List, Set, Any

import git

from .manifest_service import ManifestService
from .pr_service import PRService
from ..config.const import basedir, riko_manifests_dir, ruyi_pkgs_dir
from ..database import get_recorder
from ..database import record_command
from ..upstreams.version_fetcher import VersionFetcher
from ..utils.version_comparator import VersionComparator, VersionDiff

logger = logging.getLogger(__name__)


class VersionSyncService:
    """
    版本同步服务类

    1. 扫描所有 board-image 包的配置
    2. 获取上游版本和仓库版本
    3. 计算版本差异
    4. 执行同步操作

    """

    # 常量定义
    PACKAGES_INDEX_ROOT = basedir.parent / "packages-index"
    MANIFESTS_ROOT = PACKAGES_INDEX_ROOT / "packages" / "board-image"
    DEFAULT_REPO_OWNER = "SmulllLu"
    DEFAULT_REPO_NAME = "packages-index"
    DEFAULT_BASE_BRANCH = "pr"
    DEFAULT_BRANCH_PREFIX = "manifest-update"

    @staticmethod
    def scan_all_packages() -> Dict[str, Any]:
        """
        扫描所有 board-image 包

        :return: {package_name: package_info} 字典

        """
        packages = {}

        # 遍历 ruyi_packages/board-image 目录
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

            # 解析 riko.toml 配置文件
            try:
                with open(riko_toml, "rb") as f:
                    config = tomllib.load(f)
                nvchecker = config.get("nvchecker", {})
                entities = config.get("entities", {})

                package_name = pkg_dir.name
                packages[package_name] = {
                    "nvchecker": nvchecker,
                    "combos": entities.get("image-combo", []),
                    "riko_toml": config  # 保存完整配置供 manifest 生成使用
                }

                logger.debug(f"Scanned package: {package_name}, combos: {packages[package_name]['combos']}")

            except Exception as e:
                logger.warning(f"Failed to parse {riko_toml}: {e}")

        return packages

    @staticmethod
    def get_repo_versions(combo_name: str, include_upstream_versions: bool = True) -> Set[str]:
        """
        获取 packages-index 中已有版本

        扫描 packages-index/packages/board-image/{combo_name}/ 目录，
        从所有 .toml 文件中提取版本号。

        如果 include_upstream_versions=True，还会读取 manifest 文件中的
        upstream_version 字段，用于与上游版本进行精确匹配。

        :param combo_name: combo 名称
        :param include_upstream_versions: 是否读取 upstream_version 字段
        :return: 版本号集合

        示例:
            combo_name = "freebsd-riscv64-mini-live"
            返回: {"14.0.0", "14.2.0", "14.3.0", "15.0.0"}

            如果 include_upstream_versions=True，还会返回 manifest 文件中
            定义的 upstream_version 值（如果有的话）
        """
        # 复用 get_repo_versions_info，避免代码重复
        info = VersionSyncService.get_repo_versions_info(combo_name)
        versions = info["file_versions"].copy()

        if include_upstream_versions:
            versions.update(info["upstream_versions"])

        logger.debug(f"Found {len(versions)} versions for {combo_name}: {versions}")
        return versions

    @staticmethod
    def get_repo_versions_info(combo_name: str) -> dict:
        """
        获取 packages-index 中已有版本的详细信息

        返回一个包含版本映射信息的字典：
        {
            "file_versions": {"0.20250117.0", "0.20250219.0"},  # 文件名版本
            "upstream_versions": {"20241230_20250117", "20250130_20250219"},  # manifest中的upstream_version
            "mapping": {  # 文件名版本 -> upstream_version 的映射
                "0.20250117.0": "20241230_20250117",
                "0.20250219.0": "20250130_20250219",
            }
        }

        :param combo_name: combo 名称
        :return: 版本信息字典
        """
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
            # 提取文件名中的版本
            file_version = VersionComparator.parse_version_from_filename(manifest_file.name)
            info["file_versions"].add(file_version)

            # 读取 manifest 文件中的 upstream_version
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
    @record_command("version-sync")
    def sync_all(args: argparse.Namespace) -> None:
        """
        执行版本同步主流程

        这是 version-sync 功能的核心入口，完成以下流程：
        1. 扫描所有 board-image 包配置
        2. 从上游获取可用版本
        3. 对比 packages-index 仓库已有版本
        4. 打印变更报告（添加/删除的版本）
        5. 如果不是 dry-run，执行 Git 操作
        6. 推送分支到远程并创建 PR

        :param args: 命令行参数
            - dry_run: 预览模式，不执行实际修改
            - verbose: 详细输出模式
            - package: 指定单个包
            - github_token, repo_owner, etc.: Git 操作参数
        """
        # 初始化数据库记录器
        recorder = get_recorder()
        # 检查是否为预览模式（不实际执行修改）
        dry_run = getattr(args, 'dry_run', False)

        logger.info("=" * 70)
        logger.info("Starting version sync...")
        if dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        logger.info("=" * 70)

        # 1. 扫描所有包配置，获取 nvchecker 和 entities 信息
        packages = VersionSyncService.scan_all_packages()
        logger.info(f"Found {len(packages)} packages to scan")

        if not packages:
            logger.warning("No packages found to sync")
            return

        # 存储所有有变更的版本差异
        all_diffs = []

        # 2. 遍历每个包，对比上游版本与仓库版本
        for package_name, package_info in packages.items():
            nvchecker = package_info["nvchecker"]
            combos = package_info["combos"]

            if not nvchecker:
                logger.warning(f"No nvchecker config for {package_name}")
                continue

            if not combos:
                logger.warning(f"No combos defined for {package_name}")
                continue

            # 创建版本获取器，用于从上游获取版本列表
            fetcher = VersionFetcher.from_nvchecker(nvchecker)

            # 从上游 URL 获取所有可用版本
            upstream_versions = fetcher.fetch_all_versions()
            logger.info(f"{package_name} upstream versions: {upstream_versions}")

            # 如果获取上游版本失败（为空），跳过该包
            if not upstream_versions:
                logger.warning(f"Skipping {package_name}: no upstream versions found (possible network error)")
                continue

            # 对该包的每个 combo（镜像组合）进行版本对比
            for combo_name in combos:
                # 获取仓库版本信息和版本映射
                repo_versions_info = VersionSyncService.get_repo_versions_info(combo_name)

                # 对比版本
                comparator = VersionComparator()
                diff = comparator.compare_with_mappings(
                    package_name=package_name,
                    combo_name=combo_name,
                    upstream_versions=upstream_versions,
                    repo_versions_info=repo_versions_info
                )

                if diff.has_changes:
                    all_diffs.append(diff)
                    logger.info(f"✓ {diff.summary()}")

                    # 打印详细报告
                    if args.verbose:
                        logger.info("\n" + diff.detailed_summary() + "\n")

        # 3. 打印总结报告
        logger.info("=" * 70)
        logger.info("Version sync summary")
        logger.info("=" * 70)
        logger.info(f"Total packages scanned: {len(packages)}")
        logger.info(f"Total combos with changes: {len(all_diffs)}")

        if all_diffs:
            total_to_add = sum(len(d.to_add) for d in all_diffs)
            total_to_delete = sum(len(d.to_delete) for d in all_diffs)
            logger.info(f"Total versions to add: {total_to_add}")
            logger.info(f"Total versions to delete: {total_to_delete}")

            # 打印所有变更
            logger.info("\nChanges to be made:")
            for diff in all_diffs:
                logger.info(f"  {diff.summary()}")

        # 4. 如果是预览模式，只打印报告不执行实际操作
        if dry_run:
            logger.info("\nDry run completed. No changes were made.")
            logger.info("Run without --dry-run to apply changes.")
            return

        if not all_diffs:
            logger.info("\nNo changes to apply.")
            return

        logger.info("\nStarting Git operations...")

        # 5. 执行 Git 操作：创建分支、提交变更、推送到远程
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
        """
        执行 Git 操作并创建 PR

        1. 加载配置（GitHub token、仓库信息等）
        2. 清理 packages-index 仓库的未跟踪文件
        3. 切换到目标分支（默认为 pr）并更新
        4. 为每个包创建功能分支
        5. 删除过时的 manifest 文件
        6. 调用 ManifestService 生成新的 manifest 文件
        7. 将生成的文件复制到 packages-index 目录
        8. 提交变更
        9. 推送分支到远程

        :param diffs: 版本差异列表
        :param packages: 包信息字典（包含 riko_toml 配置）
        :param recorder: 数据库记录器
        :param args: 命令行参数
        """
        from ..config.settings import settings
        import subprocess

        # 从配置文件或命令行参数加载 GitHub 配置
        # 优先级：命令行参数 > 配置文件
        gh_token = args.github_token or settings.github_token
        repo_owner = args.repo_owner or settings.github_repo_owner or VersionSyncService.DEFAULT_REPO_OWNER
        repo_name = args.repo_name or settings.github_repo_name or VersionSyncService.DEFAULT_REPO_NAME
        base_branch = args.base_branch or settings.github_base_branch or VersionSyncService.DEFAULT_BASE_BRANCH
        branch_prefix = args.branch_prefix or settings.pr_branch_prefix or VersionSyncService.DEFAULT_BRANCH_PREFIX

        # 检查 packages-index 仓库是否存在
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

            # 清理 Git 仓库中的未跟踪文件（临时文件等）
            try:
                repo.git.clean("-fd", "-d")
                logger.info("Cleaned untracked files in packages-index")
            except git.GitError as e:
                logger.warning(f"Failed to clean untracked files: {e}")

            # 切换到目标分支（默认为 pr）并从远程拉取最新更新
            logger.info(f"Checking out base branch: {base_branch}")
            try:
                repo.git.checkout(base_branch)
                repo.git.pull("origin", base_branch)
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

            # 为每个包规划功能分支名称（格式：manifest-update/{package}-{base_branch}）
            feature_branches = {}  # {package_name: feature_branch}
            for diff in diffs:
                feature_branch = f"{branch_prefix}/{diff.package_name}-{base_branch}"
                feature_branches[diff.package_name] = feature_branch

            # 切换到或创建第一个 feature 分支
            first_diff = diffs[0]
            first_branch = feature_branches[first_diff.package_name]

            logger.info(f"Using feature branch: {first_branch}")

            # 创建或切换分支
            if first_branch in [ref.name for ref in repo.refs]:
                try:
                    repo.git.checkout(first_branch)
                    logger.info(f"Checked out existing branch: {first_branch}")
                except git.GitError as e:
                    logger.warning(f"Failed to checkout branch: {e}")

                # 尝试 rebase
                try:
                    repo.git.rebase(f"origin/{base_branch}")
                except git.GitError:
                    pass
            else:
                try:
                    repo.git.checkout("-b", first_branch, f"origin/{base_branch}")
                    logger.info(f"Created new branch: {first_branch}")
                except git.GitError as e:
                    logger.error(f"Failed to create branch: {e}")
                    raise

            # 收集所有需要删除和添加的 manifest 文件
            files_to_delete = []
            files_to_add = []

            # 按包名收集待添加版本（ManifestService.generate() 会为该包的所有 combos 生成 manifest）
            package_versions_to_add: Dict[str, Set[str]] = {}
            for diff in diffs:
                # 需要删除的文件
                if diff.to_delete:
                    for version in diff.to_delete:
                        manifest_file = VersionSyncService.MANIFESTS_ROOT / diff.combo_name / f"{version}.toml"
                        if manifest_file.exists():
                            files_to_delete.append(str(manifest_file))

                # 收集待添加版本
                if diff.to_add:
                    if diff.package_name not in package_versions_to_add:
                        package_versions_to_add[diff.package_name] = set()
                    package_versions_to_add[diff.package_name].update(diff.to_add)

            # 为每个包生成 manifest 文件并复制到 packages-index
            for package_name, versions_to_add in package_versions_to_add.items():
                logger.info(f"Generating manifests for {package_name}, versions: {sorted(versions_to_add)}")
                try:
                    # 调用 ManifestService.generate() 生成 manifest
                    # 该方法会为该包的所有 combos 生成 manifest 文件
                    # 生成的文件保存在 riko_manifests_dir 中
                    ManifestService.generate(
                        up_name=package_name,
                        gen_vers=list(versions_to_add),
                        down_grade=False
                    )

                    # 从包信息中获取完整配置，用于确定有哪些 combos
                    riko_toml = packages[package_name].get("riko_toml", {})
                    # 获取该包的所有 combos（镜像组合）
                    combos = riko_toml.get("entities", {}).get("image-combo", [])
                    for combo_name in combos:
                        for version in versions_to_add:
                            # 查找实际生成的 manifest 文件（可能包含版本前缀，如 0.20240720.0.toml）
                            combo_dir = riko_manifests_dir / "board-image" / combo_name
                            if not combo_dir.exists():
                                logger.warning(f"Combo directory not found: {combo_dir}")
                                continue

                            # 使用 glob 查找包含版本号的文件（支持 version.toml 和 0.version.0.toml 等格式）
                            manifest_files = list(combo_dir.glob(f"*{version}*.toml"))

                            if not manifest_files:
                                logger.warning(f"Manifest file not found for {combo_name} version {version}")
                                continue

                            # 如果找到多个文件，使用最新的一个
                            manifest_file = max(manifest_files, key=lambda p: p.stat().st_mtime)
                            logger.debug(f"Found manifest file: {manifest_file}")

                            # 将生成的 manifest 文件同时复制到 packages-index 目录
                            target_dir = VersionSyncService.MANIFESTS_ROOT / combo_name
                            target_file = target_dir / manifest_file.name  # 保持原文件名
                            target_dir.mkdir(parents=True, exist_ok=True)
                            import shutil
                            shutil.copy2(manifest_file, target_file)
                            files_to_add.append(str(target_file))
                            logger.info(f"✓ Generated manifest: {target_file}")

                except Exception as e:
                    logger.error(f"✗ Failed to generate manifests for {package_name}: {e}")
                    # 记录失败到数据库
                    recorder.record_pr_creation(
                        package_name=package_name,
                        version=",".join(sorted(versions_to_add)),
                        status="failed",
                        error_type=type(e).__name__,
                        error_message=str(e)
                    )
                    # 继续处理其他包，不中断整个流程

            # 从 Git 索引和工作目录中删除过时的 manifest 文件
            if files_to_delete:
                logger.info(f"Deleting {len(files_to_delete)} files...")
                try:
                    # 删除索引中的文件
                    repo.index.remove(files_to_delete)
                    # 删除工作目录中的文件
                    for f in files_to_delete:
                        try:
                            subprocess.run(["rm", "-f", f], check=True)
                            logger.debug(f"Deleted: {f}")
                        except subprocess.CalledProcessError as e:
                            logger.warning(f"Failed to delete {f}: {e}")
                except git.GitError as e:
                    logger.error(f"Failed to remove files from index: {e}")

            # 将新生成的 manifest 文件添加到 Git 索引
            if files_to_add:
                logger.info(f"Adding {len(files_to_add)} new files to git...")
                try:
                    repo.index.add(files_to_add)
                    logger.info("Added new files to git index")
                except git.GitError as e:
                    logger.error(f"Failed to add files to index: {e}")

            # 检查是否有文件变更需要提交
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

            # 推送分支到远程仓库
            if commit_msg:
                logger.info(f"Pushing branch to {repo_owner}/{repo_name}...")
                origin = repo.remote(name="origin")
                remote_url = origin.url

                # 使用 Git credential helper
                if remote_url.startswith("https://"):
                    credential_data = f"protocol=https\nhost=github.com\nusername={gh_token}\npassword=x-oauth-basic\n"
                    try:
                        subprocess.run(
                            ["git", "credential", "approve"],
                            input=credential_data,
                            capture_output=True,
                            text=True,
                            check=True,
                            cwd=VersionSyncService.PACKAGES_INDEX_ROOT
                        )
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"Failed to approve git credential: {e}")

                try:
                    repo.git.push("origin", first_branch)
                    logger.info(f"Pushed: {first_branch} -> origin/{first_branch}")
                except git.GitError as e:
                    logger.error(f"Failed to push: {e}")
                    raise

                # 清除凭据
                if remote_url.startswith("https://"):
                    try:
                        subprocess.run(
                            ["git", "credential", "reject"],
                            input=f"protocol=https\nhost=github.com\nusername={gh_token}\n",
                            capture_output=True,
                            text=True,
                            check=False,
                            cwd=VersionSyncService.PACKAGES_INDEX_ROOT
                        )
                    except Exception as e:
                        logger.debug(f"Failed to clear git credential: {e}")

                logger.info("✓ Git operations completed successfully")

                # 构建 PR 标题和描述
                total_to_add = sum(len(d.to_add) for d in diffs)
                total_to_delete = sum(len(d.to_delete) for d in diffs)
                pr_title = f"version-sync: update manifests ({total_to_add} add, {total_to_delete} remove)"

                pr_body_parts = ["Automatically synced from ruyi-packaging"]
                for diff in diffs:
                    if diff.to_add:
                        pr_body_parts.append(f"- {diff.package_name}: add {len(diff.to_add)} versions")
                    if diff.to_delete:
                        pr_body_parts.append(f"- {diff.package_name}: remove {len(diff.to_delete)} versions")
                pr_body = "\n".join(pr_body_parts)

                # 调用 PRService 创建 PR
                PRService._create_github_pr(
                    gh_token=gh_token,
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    base_branch=base_branch,
                    feature_branch=first_branch,
                    title=pr_title,
                    body=pr_body,
                    recorder=recorder,
                    package_name="version-sync",
                    version=",".join([f"{d.package_name}:{','.join(d.to_add)}" for d in diffs])
                )

        except Exception as e:
            logger.error(f"Git operations failed: {e}")
            raise