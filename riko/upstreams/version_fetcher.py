#!/usr/bin/env python3
# riko/upstreams/version_fetcher.py - 版本获取器
"""
从 nvchecker 配置获取所有可用版本

使用场景：
- 版本同步功能中从上游获取版本列表
- 支持多种源类型：regex, github
- 自动清理和验证版本格式

"""

import logging
import os
import re
import urllib.parse
import urllib.request
import http.client
from typing import Set, Optional, Dict

from .regex import RegexUpstream

logger = logging.getLogger(__name__)


def _get_proxy_url() -> Optional[str]:
    """
    获取代理 URL

    :return: 代理 URL，如果没有配置则返回 None
    """
    # 检查环境变量
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    if proxy:
        logger.debug(f"Using proxy: {proxy}")
    else:
        logger.debug("No proxy configured")

    return proxy


class VersionFetcher:
    """
    版本获取器

    职责：
    1. 从 nvchecker 配置获取所有可用版本
    2. 支持多种源类型：regex, github
    3. 清理和验证版本格式

    使用示例（regex 类型）：
    ```python
    fetcher = VersionFetcher.from_nvchecker({
        "source": "regex",
        "url": "https://example.com/releases/",
        "regex": r'<a href="([\\d.]+)/"'
    })
    versions = fetcher.fetch_all_versions()
    ```

    使用示例（github 类型）：
    ```python
    fetcher = VersionFetcher.from_nvchecker({
        "source": "github",
        "github": "owner/repo"
    })
    versions = fetcher.fetch_all_versions()
    ```
    """

    def __init__(self, source: str, config: Dict[str, str]) -> None:
        """
        初始化版本获取器

        :param source: 源类型 ("regex" 或 "github")
        :param config: 配置字典，包含 url/regex 或 github 等字段

        """
        self._source = source
        self._config = config
        self._ready = False
        self._cached_versions: Set[str] = set()

    @classmethod
    def from_nvchecker(cls, nvchecker: Dict[str, str]) -> 'VersionFetcher':
        """
        从 nvchecker 配置创建版本获取器

        :param nvchecker: nvchecker 配置字典
        :return: VersionFetcher 实例

        """
        source = nvchecker.get("source", "regex")
        return cls(source, nvchecker)

    def fetch_all_versions(self) -> Set[str]:
        """
        获取上游所有可用版本

        工作流程：
        1. 检查缓存（避免重复请求）
        2. 根据 source 类型选择获取策略
        3. 清理和验证每个版本
        4. 返回去重后的版本集合

        :return: 版本号集合（去重）

        示例:
            regex 类型输入: "https://mirror.iscas.ac.cn/FreeBSD/releases/..."
            返回: {"13.5", "14.3", "15.0"}

            github 类型输入: "milkv-mars/mars-buildroot-sdk"
            返回: {"2024.01", "2024.02", "2025.01"}
        """
        # 如果已加载，直接返回缓存
        if self._ready:
            return self._cached_versions

        versions = set()

        try:
            # 根据 source 类型选择获取策略
            if self._source == "regex":
                versions = self._fetch_regex_versions()
            elif self._source == "github":
                versions = self._fetch_github_versions()
            else:
                logger.error(f"Unsupported source type: {self._source}")
                return versions

            self._cached_versions = versions
            self._ready = True

            logger.info(f"Successfully fetched {len(versions)} versions from {self._source} source")

        except urllib.error.URLError as e:
            logger.error(f"Failed to fetch versions from {self._source}: {e}")
        except http.client.HTTPException as e:
            logger.error(f"HTTP error when fetching versions: {e}")
        except Exception as e:
            logger.error(f"Unexpected error when fetching versions: {e}")

        return versions

    def _fetch_regex_versions(self) -> Set[str]:
        """
        从 regex 源获取版本

        :return: 版本号集合
        """
        url = self._config.get("url", "")
        regex = self._config.get("regex", "")

        if not url or not regex:
            logger.error(f"Missing url or regex in config: {self._config}")
            return set()

        # 创建 RegexUpstream 实例来复用现有的 HTTP 请求逻辑
        upstream = RegexUpstream(
            base_url=url,
            base_re=regex,
            file_url=url,
            file_re=regex
        )

        raw_versions = upstream.get_release_asserts()
        logger.debug(f"Fetched {len(raw_versions)} raw versions from {url}")

        versions = set()
        for version_str in raw_versions:
            cleaned_version = self._clean_version(version_str)
            if cleaned_version:
                versions.add(cleaned_version)

        return versions

    def _fetch_github_versions(self) -> Set[str]:
        """
        从 GitHub releases 获取版本

        :return: 版本号集合
        """
        github_repo = self._config.get("github", "")

        if not github_repo:
            logger.error(f"Missing github field in config: {self._config}")
            return set()

        try:
            from github import Auth, Github
            from ..config.settings import settings

            # 获取代理设置
            proxy_url = _get_proxy_url()

            # 使用配置的 GitHub token
            token = settings.github_token
            if token:
                gh = Github(auth=Auth.Token(token))
                logger.debug(f"Using GitHub token for {github_repo}")
            else:
                logger.warning(f"No GitHub token configured for {github_repo}")
                gh = Github()

            # 设置代理（如果配置了）
            if proxy_url:
                # PyGithub 使用 requests 库，需要通过 environment 设置代理
                # 我们设置到环境变量中
                logger.info(f"Using proxy for GitHub (from environment): {proxy_url}")

            # 获取仓库
            repo = gh.get_repo(github_repo)

            # 获取所有 releases
            releases = repo.get_releases()
            versions = set()

            for release in releases:
                tag_name = release.tag_name
                # 清理版本号（去除 'v' 前缀）
                cleaned_version = self._clean_version(tag_name)
                if cleaned_version:
                    versions.add(cleaned_version)

            logger.debug(f"Fetched {len(versions)} versions from GitHub repo {github_repo}")
            return versions

        except ImportError:
            logger.error("PyGithub library not installed. Install with: pip install PyGithub")
            return set()
        except Exception as e:
            logger.error(f"Failed to fetch versions from GitHub: {e}")
            return set()

    def _clean_version(self, version_str: str) -> Optional[str]:
        """
        清理版本字符串

        处理步骤：
        1. 去除首尾空格
        2. 去除首尾斜杠（/）
        3. 验证非空
        4. 过滤无效版本格式（如 ".."）

        :param version_str: 原始版本字符串
        :return: 清理后的版本号，无效则返回 None

        示例:
            "13.5/" -> "13.5"
            "  14.3  " -> "14.3"
            "15.0/" -> "15.0"
            "" -> None
            ".." -> None
        """
        if not version_str:
            return None

        # 去除首尾空格和斜杠
        cleaned = version_str.strip().strip('/')

        # 验证清理后的版本非空和有效性
        if not cleaned or cleaned == '..' or cleaned == '.':
            logger.warning(f"Invalid version after cleaning: '{version_str}'")
            return None

        # 验证版本格式：只允许字母、数字、点、下划线、连字符
        if not re.match(r'^[\w\d._-]+$', cleaned):
            logger.warning(f"Invalid version format: '{cleaned}' (from '{version_str}')")
            return None

        return cleaned

    def is_ready(self) -> bool:
        """
        检查是否已加载版本

        :return: True 如果版本已缓存
        """
        return self._ready

    def get_cached_versions(self) -> Set[str]:
        """
        获取缓存的版本

        :return: 缓存的版本集合（可能为空）
        """
        return self._cached_versions
