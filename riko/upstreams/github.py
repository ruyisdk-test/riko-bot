# -*- coding: utf-8 -*-
"""
GitHub 上游源实现

该模块提供了 GitHub Release 资源的访问接口，用于获取 GitHub 仓库发布版本的资产文件信息。
支持使用 GitHub Token 进行认证，提高 API 请求的速率限制。
"""

import logging
import re
import tomllib

from github import Auth, Github
from typing import ClassVar, Dict, List, Tuple

from .upstream import Upstream
from ..config.const import nvchecker_key


logger = logging.getLogger(__name__)


class GithubUpstream(Upstream):
    """
    GitHub 上游源实现类

    该类实现了 Upstream 协议，提供访问 GitHub Release 资产的功能。
    可以获取特定 release 版本的所有资产文件，并支持按子字符串或正则表达式进行筛选。

    Attributes:
        source: 类变量，标识此上游源的类型为 "github"
        _release: 目标 release 版本标签（如 "v1.0.0"）
        _github: PyGithub 的 Github 客户端实例
        _repo: PyGithub 的 Repository 对象
        _cache_asserts: 缓存已获取的资产列表，避免重复请求 API
    """

    source: ClassVar[str] = "github"

    def __init__(self, repo: str, release: str) -> None:
        """
        初始化 GitHub 上游源

        Args:
            repo: GitHub 仓库标识，格式为 "owner/repo"（如 "ruyisdk/packages-index"）
            release: Release 版本标签（如 "v1.0.0" 或 "0.20250101.0"）

        Note:
            如果 nvchecker_key 配置文件存在且包含 GitHub token，
            将使用该 token 进行认证，以提高 API 请求速率限制。
            否则以未认证模式访问，可能会受到更严格的速率限制。
        """
        self._release = release

        # 尝试从 nvchecker 配置文件中加载 GitHub token
        if nvchecker_key.exists() and nvchecker_key.is_file():
            with open(nvchecker_key, "rb") as kf:
                key = tomllib.load(kf).get("keys")
                if key is not None:
                    key = key.get("github")

            # 如果找到 token，使用认证模式；否则使用未认证模式
            if key is not None:
                self._github = Github(auth=Auth.Token(key))
            else:
                self._github = Github()

        else:
            logger.warning(f"nvchecker keyfile {nvchecker_key} not found.")
            self._github = Github()

        # 获取目标仓库对象
        self._repo = self._github.get_repo(repo)

        # 初始化资产缓存
        # 结构: {release_tag: [(asset_name, download_url), ...]}
        self._cache_asserts: Dict[str, List[Tuple[str, str]]] = {}

    def get_release_asserts_obj(self):
        """
        获取 Release 资产的原始 PyGithub 对象列表

        Returns:
            PyGithub 的 NamedUser 对象列表，包含所有资产的详细信息

        Note:
            此方法返回原始对象，通常供内部使用。外部调用建议使用 get_release_asserts()
        """
        release = self._repo.get_release(self._release)
        return release.get_assets()

    def get_release_asserts(self) -> List[Tuple[str, str]]:
        """
        获取指定 Release 的所有资产文件列表

        Returns:
            资产文件列表，每个元素为元组 (文件名, 下载URL)

        Note:
            该方法会缓存结果，首次调用后会从 GitHub API 获取数据并缓存，
            后续调用直接返回缓存数据，避免重复请求 API。
        """
        assets = self.get_release_asserts_obj()

        # 检查缓存
        if self._release in self._cache_asserts:
            return self._cache_asserts[self._release]

        # 提取资产名称和下载链接
        files: List[Tuple[str, str]] = []
        for asset in assets:
            files.append((asset.name, asset.browser_download_url))
        self._cache_asserts[self._release] = files

        return files

    def get_release_asserts_substring(self, substr: str) -> List[Tuple[str, str]]:
        """
        按文件名子字符串筛选资产文件

        Args:
            substr: 要匹配的子字符串，如 "x86_64" 或 "rootfs"

        Returns:
            匹配的资产文件列表，每个元素为元组 (文件名, 下载URL)

        Example:
            >>> upstream.get_release_asserts_substring("x86_64")
            [("image-x86_64.zip", "https://..."), ...]
        """
        r = []

        for f in self.get_release_asserts():
            if substr in f[0]:
                r.append(f)

        return r

    def get_release_assert_substring(self, substr: str) -> Tuple[str, str]:
        """
        按文件名子字符串筛选，确保只返回唯一结果

        Args:
            substr: 要匹配的子字符串

        Returns:
            单个匹配的资产文件元组 (文件名, 下载URL)

        Raises:
            AssertionError: 如果匹配结果不唯一

        Example:
            >>> upstream.get_release_assert_substring("x86_64")
            ("image-x86_64.zip", "https://...")
        """
        r = self.get_release_asserts_substring(substr)

        assert len(r) == 1
        return r[0]

    def get_release_asserts_regex(self, pattern: str) -> List[Tuple[str, str]]:
        """
        按正则表达式筛选资产文件

        Args:
            pattern: 正则表达式模式，从文件名开头匹配

        Returns:
            匹配的资产文件列表，每个元素为元组 (文件名, 下载URL)

        Note:
            使用 re.match() 进行匹配，只匹配文件名开头

        Example:
            >>> upstream.get_release_asserts_regex(r".*-x86_64\\.zip")
            [("image-x86_64.zip", "https://..."), ...]
        """
        r = []

        for f in self.get_release_asserts():
            if re.match(pattern, f[0]):
                r.append(f)

        return r

    def get_release_assert_regex(self, pattern: str) -> Tuple[str, str]:
        """
        按正则表达式筛选，确保只返回唯一结果

        Args:
            pattern: 正则表达式模式

        Returns:
            单个匹配的资产文件元组 (文件名, 下载URL)

        Raises:
            AssertionError: 如果匹配结果不唯一

        Example:
            >>> upstream.get_release_assert_regex(r".*-x86_64\\.zip")
            ("image-x86_64.zip", "https://...")
        """
        r = self.get_release_asserts_regex(pattern)

        assert len(r) == 1
        return r[0]
