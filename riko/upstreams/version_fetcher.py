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
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    if proxy:
        logger.debug(f"Using proxy: {proxy}")
    else:
        logger.debug("No proxy configured")

    return proxy


class VersionFetcher:

    def __init__(self, source: str, config: Dict[str, str]) -> None:
        self._source = source
        self._config = config
        self._ready = False
        self._cached_versions: Set[str] = set()

    @classmethod
    def from_nvchecker(cls, nvchecker: Dict[str, str]) -> 'VersionFetcher':
        source = nvchecker.get("source", "regex")
        return cls(source, nvchecker)

    def fetch_all_versions(self) -> Set[str]:
        if self._ready:
            return self._cached_versions

        versions = set()

        try:
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
        url = self._config.get("url", "")
        regex = self._config.get("regex", "")

        if not url or not regex:
            logger.error(f"Missing url or regex in config: {self._config}")
            return set()

        # Reuse RegexUpstream's HTTP request logic
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
        github_repo = self._config.get("github", "")

        if not github_repo:
            logger.error(f"Missing github field in config: {self._config}")
            return set()

        try:
            from github import Auth, Github
            from ..config.settings import settings

            proxy_url = _get_proxy_url()

            token = settings.github_token
            if token:
                gh = Github(auth=Auth.Token(token))
                logger.debug(f"Using GitHub token for {github_repo}")
            else:
                logger.warning(f"No GitHub token configured for {github_repo}")
                gh = Github()

            if proxy_url:
                # PyGithub uses requests; the proxy is set via the environment
                logger.info(f"Using proxy for GitHub (from environment): {proxy_url}")

            repo = gh.get_repo(github_repo)

            releases = repo.get_releases()
            versions = set()

            for release in releases:
                tag_name = release.tag_name
                # Strip the 'v' prefix
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
        if not version_str:
            return None

        cleaned = version_str.strip().strip('/')

        if not cleaned or cleaned == '..' or cleaned == '.':
            logger.warning(f"Invalid version after cleaning: '{version_str}'")
            return None

        # Only allow letters, digits, dots, underscores, and hyphens
        if not re.match(r'^[\w\d._-]+$', cleaned):
            logger.warning(f"Invalid version format: '{cleaned}' (from '{version_str}')")
            return None

        return cleaned

    def is_ready(self) -> bool:
        return self._ready

    def get_cached_versions(self) -> Set[str]:
        return self._cached_versions
