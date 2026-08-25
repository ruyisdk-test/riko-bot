#!/usr/bin/env python3

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
from ..database import record_command
from ..database import get_recorder

import git
from github import Auth, Github
from github.GithubException import GithubException


logger = logging.getLogger(__name__)


class PRError(Exception):
    pass


class TokenNotFoundError(PRError):
    pass


class RepositoryNotFoundError(PRError):
    pass


class ManifestNotFoundError(PRError):
    pass


class PRService:
    PACKAGES_INDEX_ROOT = basedir.parent / "packages-index"
    TARGET_MANIFEST_ROOT = PACKAGES_INDEX_ROOT / "manifests"
    CORE_DIR = "board-image"

    @staticmethod
    def _create_github_pr(
        gh_token: str,
        repo_owner: str,
        repo_name: str,
        base_branch: str,
        feature_branch: str,
        title: str,
        body: str,
        recorder,
        package_name: str,
        version: str
    ) -> bool:
        logger.info(f"Creating PR to {repo_owner}/{repo_name} (base: {base_branch})...")
        try:
            auth = Auth.Token(gh_token)
            g = Github(auth=auth, timeout=30)
        except (ImportError, AttributeError):
            g = Github(gh_token, timeout=30)

        try:
            gh_repo = g.get_repo(f"{repo_owner}/{repo_name}")

            existing_prs = gh_repo.get_pulls(
                state="open",
                head=f"{repo_owner}:{feature_branch}",
                base=base_branch
            )

            if existing_prs.totalCount > 0:
                logger.info(f"PR already exists: {repo_owner}/{repo_name}#{existing_prs[0].number}")

                # Update nvchecker old version to avoid re-detecting this update
                PRService._update_nvchecker_old_version(package_name, version)

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
                return True

            pr = gh_repo.create_pull(
                title=title,
                body=body,
                head=feature_branch,
                base=base_branch
            )
            logger.info(f"PR created successfully: {pr.html_url}")

            # Update nvchecker old version to avoid re-detecting this update
            PRService._update_nvchecker_old_version(package_name, version)

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
            return True

        except GithubException as e:
            logger.error(f"GitHub API failed: {e}")
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
            raise

    @staticmethod
    def _load_riko_config() -> Dict[str, Any]:
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
        try:
            if not nvchecker_old_ver.exists():
                logger.warning(f"[nvchecker] old_ver.json not found: {nvchecker_old_ver}")
                return False

            with open(nvchecker_old_ver, 'r', encoding='utf-8') as f:
                data = json.load(f)

            current_version = data.get("data", {}).get(package_name, {}).get("version")
            if current_version == version:
                logger.debug(f"[nvchecker] {package_name} version already up to date: {version}")
                return True

            if "data" not in data:
                data["data"] = {}
            if package_name not in data["data"]:
                data["data"][package_name] = {}
            data["data"][package_name]["version"] = version

            # Atomic write via temp file + replace
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
        ruyi_pkgs = get_riko().get_ruyi_packages()
        upstream_config = ruyi_pkgs.get_upstreams().get(package_name)

        if not upstream_config:
            search_path = riko_manifests_dir / PRService.CORE_DIR / package_name
            manifest_files = list(search_path.glob("*.toml"))

            # Fallback to a recursive search
            if not manifest_files:
                manifest_files = list(riko_manifests_dir.rglob(f"{PRService.CORE_DIR}/*{package_name}*.toml"))
            return manifest_files

        combos = upstream_config.get_combos()
        manifest_files = []

        for combo in combos:
            search_path = riko_manifests_dir / PRService.CORE_DIR / combo
            combo_manifests = list(search_path.glob("*.toml"))
            if combo_manifests:
                manifest_files.extend(combo_manifests)

        return manifest_files

    @staticmethod
    def _sync_manifest_to_packages_index(cache_file: Path) -> Path:
        relative_path = cache_file.relative_to(riko_manifests_dir)
        target_file = PRService.TARGET_MANIFEST_ROOT / relative_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_file, target_file)
        logger.info(f"Synced manifest: {cache_file} -> {target_file}")

        return target_file

    @staticmethod
    @record_command("pr")
    def create(args: argparse.Namespace) -> None:
        recorder = get_recorder()

        config = PRService._load_riko_config()
        gh_token = args.github_token or config["github"]["token"]
        repo_owner = args.repo_owner or config["github"]["repo_owner"]
        repo_name = args.repo_name or config["github"]["repo_name"]
        base_branch = args.base_branch or config["github"]["base_branch"]
        branch_prefix = args.branch_prefix or config["pr"]["branch_prefix"]
        package_name = args.package_name
        feature_branch = f"{branch_prefix}/{package_name}-{base_branch}"

        if not gh_token:
            recorder.record_pr_creation(
                package_name=package_name,
                version="",
                status="failed",
                error_type="ValueError",
                error_message="No valid GitHub token found"
            )
            raise TokenNotFoundError("No valid GitHub token found")

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
        # Version is the last dash-separated segment of the filename
        version = cache_manifests[0].stem.split("-")[-1]

        logger.info("Operating on packages-index git repository...")

        repo.git.checkout("pr")
        repo.git.pull("origin", "pr")

        logger.info("Syncing manifests to packages-index...")
        target_manifests = []
        for cache_file in cache_manifests:
            target_file = PRService._sync_manifest_to_packages_index(cache_file)
            target_manifests.append(target_file)

        if feature_branch in [ref.name for ref in repo.refs]:
            repo.git.checkout(feature_branch)
        else:
            repo.git.checkout("-b", feature_branch)

        repo.index.add([str(f) for f in target_manifests])

        if not repo.is_dirty():
            logger.info(f"No changes to commit for {package_name} version {version}")
            logger.info(f"The manifest may already exist in the base branch")

            # Manifest already exists, so mark the version as seen
            PRService._update_nvchecker_old_version(package_name, version)

            recorder.record_pr_creation(
                package_name=package_name,
                version=version,
                status="skipped",
                skip_reason="no_changes"
            )
            return

        commit_msg = f"manifest: update {package_name} to {version} (board-image)"
        repo.index.commit(commit_msg)
        logger.info(f"Committed: {commit_msg}")

        # Push via credential helper to avoid leaking the token in the URL
        logger.info(f"Pushing branch to {repo_owner}/{repo_name}...")
        origin = repo.remote(name="origin")
        remote_url = origin.url

        if remote_url.startswith("https://"):
            import subprocess

            credential_data = f"protocol=https\nhost=github.com\nusername={gh_token}\npassword=x-oauth-basic\n"

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
                logger.warning("Falling back to direct URL authentication (less secure)")

        try:
            repo.git.pull("origin", feature_branch, rebase=True)
        except git.GitError:
            pass  # Ignore rebase failure

        repo.git.push("origin", feature_branch)

        if remote_url.startswith("https://"):
            try:
                subprocess.run(
                    ["git", "credential", "reject"],
                    input=f"protocol=https\nhost=github.com\nusername={gh_token}\n",
                    capture_output=True,
                    text=True,
                    check=False,  # clearing failure is non-fatal
                    cwd=PRService.PACKAGES_INDEX_ROOT
                )
            except Exception as e:
                logger.debug(f"Failed to clear git credential: {e}")

        logger.info(f"Pushed: {feature_branch} -> origin/{feature_branch}")

        PRService._create_github_pr(
            gh_token=gh_token,
            repo_owner=repo_owner,
            repo_name=repo_name,
            base_branch=base_branch,
            feature_branch=feature_branch,
            title=f"Update {package_name} to {version}",
            body=f"""Automatically synced from ruyi-packaging
- Package: {package_name}
- Version: {version}
- Manifest Path: {target_manifests[0].relative_to(PRService.PACKAGES_INDEX_ROOT)}""",
            recorder=recorder,
            package_name=package_name,
            version=version
        )
