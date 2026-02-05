#!/usr/bin/env python3
# riko/services/pr_service.py - GitHub PR 创建服务
"""
实现 PR 创建服务，用于自动创建 GitHub PR
功能：
1. 查找缓存中的清单文件
2. 同步到 packages-index 仓库
3. 创建 git 分支并提交
4. 通过 GitHub API 创建 PR

"""

import argparse
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..config.settings import settings
from ..config.const import basedir, riko_manifests_dir, nvchecker_old_ver
from ..core import get_riko
from ..database import record_command  # 数据库记录装饰器
from ..database import get_recorder  # 数据库记录器

# GitPython: Git 操作库（类似于 Java's JGit）
import git
# PyGithub: GitHub API 客户端（类似于 Java's github-api）
from github import Auth, Github
from github.GithubException import GithubException


logger = logging.getLogger(__name__)


# 自定义异常类
class PRError(Exception):
    """PR 命令的基础异常类"""
    pass


class TokenNotFoundError(PRError):
    """Token 未找到异常"""
    pass


class RepositoryNotFoundError(PRError):
    """仓库不存在异常"""
    pass


class ManifestNotFoundError(PRError):
    """清单文件未找到异常"""
    pass


# PR 服务类
class PRService:
    """PR 创建服务类"""

    # 常量定义
    # packages-index 仓库路径（在项目根目录的上一级）
    PACKAGES_INDEX_ROOT = basedir.parent / "packages-index"
    # 清单文件目标根目录
    TARGET_MANIFEST_ROOT = PACKAGES_INDEX_ROOT / "manifests"
    # 核心分类目录
    CORE_DIR = "board-image"

    @staticmethod
    def _load_riko_config() -> Dict[str, Any]:
        """从统一配置系统加载 riko 配置"""
        return {
            "github": {
                "token": settings.github_token,
                "repo_owner": settings.github_repo_owner or "SmulllLu",
                "repo_name": settings.github_repo_name or "packages-index",
                "base_branch": settings.github_base_branch or "pr"
            },
            "pr": {
                "branch_prefix": settings.pr_branch_prefix or "manifest-update"
            }
        }

    @staticmethod
    def _update_nvchecker_old_version(package_name: str, version: str) -> bool:
        """
        更新 nvchecker 的 old_ver.json 文件

        在 PR 创建成功后调用，避免下次运行时重复检测已处理的版本

        :param package_name: 包名
        :param version: 版本号
        :return: 更新成功返回 True，失败返回 False
        """
        try:
            if not nvchecker_old_ver.exists():
                logger.warning(f"[nvchecker] old_ver.json not found: {nvchecker_old_ver}")
                return False

            # 读取 old_ver.json
            with open(nvchecker_old_ver, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 检查版本是否需要更新（避免不必要的写入）
            current_version = data.get("data", {}).get(package_name, {}).get("version")
            if current_version == version:
                logger.debug(f"[nvchecker] {package_name} version already up to date: {version}")
                return True

            # 更新版本
            if "data" not in data:
                data["data"] = {}
            if package_name not in data["data"]:
                data["data"][package_name] = {}
            data["data"][package_name]["version"] = version

            # 写回文件（原子操作）
            temp_file = nvchecker_old_ver.with_suffix('.json.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(nvchecker_old_ver)

            logger.info(f"[nvchecker] Updated old_ver.json: {package_name} → {version}")
            return True

        except Exception as e:
            logger.error(f"[nvchecker] Failed to update old_ver.json: {e}")
            return False

    @staticmethod
    def _find_manifest_in_cache(package_name: str) -> List[Path]:
        """
        在 riko 缓存目录中查找清单文件

        查找策略：
        1. 如果 package_name 对应的 upstream 配置存在：
           - 根据 combos 列表查找每个 combo 的清单
        2. 如果不存在：
           - 直接在 board-image/{package_name}/ 目录查找
           - 使用递归全局搜索（rglob）

        :param package_name: 上游包名称（例如："LicheeRV-Nano-Build"）
        :return: 清单文件路径列表
        """
        # 获取 ruyi_packages 配置
        ruyi_pkgs = get_riko().get_ruyi_packages()
        upstream_config = ruyi_pkgs.get_upstreams().get(package_name)

        # 方法1: 如果 upstream 配置不存在，使用直接搜索
        if not upstream_config:
            search_path = riko_manifests_dir / PRService.CORE_DIR / package_name
            manifest_files = list(search_path.glob("*.toml"))  # 查找所有 .toml 文件

            # 如果找不到，使用递归搜索
            if not manifest_files:
                # rglob: 递归全局搜索（类似于 find 命令）
                manifest_files = list(riko_manifests_dir.rglob(f"{PRService.CORE_DIR}/*{package_name}*.toml"))
            return manifest_files

        # 方法2: 根据 combos 列表查找
        combos = upstream_config.get_combos()
        manifest_files = []

        for combo in combos:
            search_path = riko_manifests_dir / PRService.CORE_DIR / combo
            combo_manifests = list(search_path.glob("*.toml"))
            if combo_manifests:
                manifest_files.extend(combo_manifests)  # 列表扩展（类似于 Java's List.addAll()）

        return manifest_files

    # 将清单文件从缓存同步到 packages-index 仓库
    @staticmethod
    def _sync_manifest_to_packages_index(cache_file: Path) -> Path:
        """
        将清单文件从缓存同步到 packages-index 仓库

        :param cache_file: 缓存中的清单文件路径
        :return: 目标文件路径

        Python 特殊语法：
        - .relative_to(): 计算相对路径（类似于 Java's Path.relativize()）
        - shutil.copy2(): 复制文件（保留元数据，类似于 Java's Files.copy()）
        """
        # 计算相对路径（相对于 riko_manifests_dir）
        # 例如：cache/riko/manifests/board-image/xxx.toml -> board-image/xxx.toml
        relative_path = cache_file.relative_to(riko_manifests_dir)

        # 构建目标文件路径
        target_file = PRService.TARGET_MANIFEST_ROOT / relative_path

        # 创建目标目录（如果不存在）
        # parents=True: 递归创建父目录
        # exist_ok=True: 如果目录已存在不报错
        target_file.parent.mkdir(parents=True, exist_ok=True)

        # 复制文件（copy2 保留文件元数据）
        shutil.copy2(cache_file, target_file)
        logger.info(f"Synced manifest: {cache_file} -> {target_file}")

        return target_file

    @staticmethod
    @record_command("pr")
    def create(args: argparse.Namespace) -> None:
        """
        Create PR to packages-index repository

        使用装饰器自动管理数据库记录：
        - 自动调用 start_scan() 开始扫描
        - 异常自动捕获并调用 finish_scan(status="failed")
        - 具体的错误记录由本方法内的 recorder.record_pr_creation() 完成

        :param args: Parsed command line arguments
        :raises PRError: PR 相关的异常
        :raises TokenNotFoundError: Token 未找到
        :raises RepositoryNotFoundError: 仓库不存在
        :raises ManifestNotFoundError: 清单未找到
        """
        # 初始化记录器（装饰器已自动调用 start_scan）
        recorder = get_recorder()

        config = PRService._load_riko_config()
        gh_token = args.github_token or config["github"]["token"]
        repo_owner = args.repo_owner or config["github"]["repo_owner"]
        repo_name = args.repo_name or config["github"]["repo_name"]
        base_branch = args.base_branch or config["github"]["base_branch"]
        branch_prefix = args.branch_prefix or config["pr"]["branch_prefix"]
        package_name = args.package_name
        feature_branch = f"{branch_prefix}/{package_name}-{base_branch}"

        # 验证 Token
        if not gh_token:
            recorder.record_pr_creation(
                package_name=package_name,
                version="",
                status="failed",
                error_type="ValueError",
                error_message="No valid GitHub token found"
            )
            raise TokenNotFoundError("No valid GitHub token found")

        # 验证仓库
        if not PRService.PACKAGES_INDEX_ROOT.exists():
            recorder.record_pr_creation(
                package_name=package_name,
                version="",
                status="failed",
                error_type="FileNotFoundError",
                error_message=f"packages-index repository not found: {PRService.PACKAGES_INDEX_ROOT}"
            )
            raise RepositoryNotFoundError(f"packages-index repository not found: {PRService.PACKAGES_INDEX_ROOT}")

        repo = git.Repo(PRService.PACKAGES_INDEX_ROOT)

        # 查找清单文件
        logger.info(f"Finding manifests for {package_name}...")

        cache_manifests = PRService._find_manifest_in_cache(package_name)
        if not cache_manifests:
            recorder.record_pr_creation(
                package_name=package_name,
                version="",
                status="failed",
                error_type="FileNotFoundError",
                error_message=f"No manifests found for {package_name}"
            )
            raise ManifestNotFoundError(f"No manifests found for {package_name}")

        logger.info(f"Found {len(cache_manifests)} manifests")
        # 提取版本号（假设清单文件名格式为：package-name-version.toml）
        version = cache_manifests[0].stem.split("-")[-1]

        # Git 操作
        logger.info("Operating on packages-index git repository...")

        repo.git.checkout("pr")
        repo.git.pull("origin", "pr")

        logger.info("Syncing manifests to packages-index...")
        target_manifests = []
        # 同步每个清单文件到 packages-index
        for cache_file in cache_manifests:
            target_file = PRService._sync_manifest_to_packages_index(cache_file)
            target_manifests.append(target_file)

        if feature_branch in [ref.name for ref in repo.refs]:
            repo.git.checkout(feature_branch)
        else:
            repo.git.checkout("-b", feature_branch)

        # 添加到暂存区
        repo.index.add([str(f) for f in target_manifests])

        # 检查是否有更改
        if not repo.is_dirty():
            logger.info(f"No changes to commit for {package_name} version {version}")
            logger.info(f"The manifest may already exist in the base branch")

            # 更新 nvchecker 版本记录（manifest 已存在，不需要重复检测）
            PRService._update_nvchecker_old_version(package_name, version)

            # 记录跳过状态并正常返回
            recorder.record_pr_creation(
                package_name=package_name,
                version=version,
                status="skipped",
                skip_reason="no_changes"
            )
            return  # 正常返回，装饰器会调用 finish_scan(status="completed")

        # 提交更改
        commit_msg = f"manifest: update {package_name} to {version} (board-image)"
        repo.index.commit(commit_msg)
        logger.info(f"Committed: {commit_msg}")

        # 推送到远程（使用安全的认证方式，避免 token 在 URL 中泄露）
        logger.info(f"Pushing branch to {repo_owner}/{repo_name}...")
        origin = repo.remote(name="origin")
        remote_url = origin.url

        # 使用 Git credential helper 来安全地处理认证
        # 这种方式避免了将 token 直接嵌入 URL，更安全
        if remote_url.startswith("https://"):
            import subprocess

            # 准备 credential 数据
            credential_data = f"protocol=https\nhost=github.com\nusername={gh_token}\npassword=x-oauth-basic\n"

            # 使用 git credential approve 来临时添加凭据
            # 这会将凭据存储在 Git 的内存缓存中，而不是在 URL 中
            try:
                subprocess.run(
                    ["git", "credential", "approve"],
                    input=credential_data,
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=PRService.PACKAGES_INDEX_ROOT
                )
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to approve git credential: {e}")
                # 如果 credential helper 失败，回退到直接使用 URL
                # 但会在日志中警告
                logger.warning("Falling back to direct URL authentication (less secure)")

        try:
            repo.git.pull("origin", feature_branch, rebase=True)
        except git.GitError:
            pass  # 忽略 rebase 失败

        repo.git.push("origin", feature_branch)

        # 推送完成后清除凭据缓存
        if remote_url.startswith("https://"):
            try:
                subprocess.run(
                    ["git", "credential", "reject"],
                    input=f"protocol=https\nhost=github.com\nusername={gh_token}\n",
                    capture_output=True,
                    text=True,
                    check=False,  # 不检查错误，因为清除失败不是致命问题
                    cwd=PRService.PACKAGES_INDEX_ROOT
                )
            except Exception as e:
                logger.debug(f"Failed to clear git credential: {e}")

        logger.info(f"Pushed: {feature_branch} -> origin/{feature_branch}")

        # 创建 GitHub PR
        logger.info(f"Creating PR to {repo_owner}/{repo_name} (base: {base_branch})...")
        try:
            auth = Auth.Token(gh_token)
            g = Github(auth=auth, timeout=30)
        except (ImportError, AttributeError):
            g = Github(gh_token, timeout=30)

        try:
            gh_repo = g.get_repo(f"{repo_owner}/{repo_name}")

            # 检查 PR 是否已存在
            existing_prs = gh_repo.get_pulls(
                state="open",
                head=f"{repo_owner}:{feature_branch}",
                base=base_branch
            )

            if existing_prs.totalCount > 0:
                logger.info(f"PR already exists: {repo_owner}/{repo_name}#{existing_prs[0].number}")

                # 更新 nvchecker 版本记录（避免重复检测）
                PRService._update_nvchecker_old_version(package_name, version)

                # 记录已存在状态并返回
                recorder.record_pr_creation(
                    package_name=package_name,
                    version=version,
                    status="already_exists",
                    pr_number=existing_prs[0].number,
                    pr_url=existing_prs[0].html_url,
                    branch_name=feature_branch,
                    repo_owner=repo_owner,
                    repo_name=repo_name
                )
                return  # 正常返回

            # 创建新 PR
            pr = gh_repo.create_pull(
                title=f"Update {package_name} to {version}",
                body=f"""Automatically synced from ruyi-packaging
- Package: {package_name}
- Version: {version}
- Manifest Path: {target_manifests[0].relative_to(PRService.PACKAGES_INDEX_ROOT)}""",
                head=feature_branch,
                base=base_branch
            )
            logger.info(f"PR created successfully: {pr.html_url}")

            # 更新 nvchecker 版本记录（避免重复检测）
            PRService._update_nvchecker_old_version(package_name, version)

            # 记录成功
            recorder.record_pr_creation(
                package_name=package_name,
                version=version,
                status="success",
                pr_number=pr.number,
                pr_url=pr.html_url,
                branch_name=feature_branch,
                repo_owner=repo_owner,
                repo_name=repo_name
            )
        # 失败时记录异常信息
        except GithubException as e:
            logger.error(f"GitHub API failed: {e}")
            # 记录失败并抛出异常（装饰器会捕获）
            error_details = json.dumps({
                "error_type": "GithubException",
                "error_message": str(e),
                "error_code": getattr(e, 'status', None)
            })
            recorder.record_pr_creation(
                package_name=package_name,
                version=version,
                status="failed",
                error_type="GithubException",
                error_message=str(e),
                error_details=error_details
            )
            raise  # 重新抛出异常，装饰器会记录并调用 finish_scan(status="failed")
