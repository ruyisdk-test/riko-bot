import http.client
import logging
import os
import re
import urllib.parse
import urllib.request

from typing import ClassVar, Dict, List, Optional, Tuple

from .upstream import Upstream

logger = logging.getLogger(__name__)


def _get_proxy_handler():
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')

    proxies = {}
    if http_proxy:
        proxies['http'] = http_proxy
        logger.debug(f"Using HTTP proxy: {http_proxy}")
    if https_proxy:
        proxies['https'] = https_proxy
        logger.debug(f"Using HTTPS proxy: {https_proxy}")

    if proxies:
        return urllib.request.ProxyHandler(proxies)
    return None


class RegexUpstream(Upstream):
    source: ClassVar[str] = "regex"

    def __init__(self, base_url: str, base_re: str, file_url: str, file_re: str) -> None:
        self._base_url = base_url
        self._base_regex = base_re
        self._file_url = file_url
        self._file_regex = file_re

        self._ready = False
        self._text = ""
        self._asserts: List[str] = []

    def _file_name_and_url(self, f: str) -> Tuple[str, str]:
        return f, urllib.parse.urljoin(self._file_url, f)

    def get_release_asserts(self) -> List[str]:
        if self._ready:
            return self._asserts

        proxy_handler = _get_proxy_handler()
        opener = urllib.request.build_opener(proxy_handler) if proxy_handler else urllib.request.build_opener()
        urllib.request.install_opener(opener)

        resp: http.client.HTTPResponse = opener.open(self._file_url, timeout=30.0)

        if resp.status != http.client.OK:
            raise RuntimeError(f"url {self._file_url} returned status code {resp.status}: "
                               f"{http.client.responses[resp.status]}")

        self._text = resp.read().decode()

        self._asserts = re.findall(self._file_regex, self._text)

        self._ready = True

        return self._asserts

    def get_release_asserts_substring(self, substr: str) -> List[Tuple[str, str]]:
        r = []

        for f in self.get_release_asserts():
            if substr in f:
                r.append(self._file_name_and_url(f))

        return r

    def get_release_assert_substring(self, substr: str) -> Tuple[str, str]:
        r = self.get_release_asserts_substring(substr)

        assert len(r) == 1, f"Expected 1 result, got {len(r)}"
        return r[0]

    def get_release_asserts_regex(self, pattern: str) -> List[Tuple[str, str]]:
        r = []

        for f in self.get_release_asserts():
            if re.search(pattern, f):
                r.append(self._file_name_and_url(f))

        return r

    def get_release_assert_regex(self, pattern: str) -> Tuple[str, str]:
        r = self.get_release_asserts_regex(pattern)

        assert len(r) == 1, f"Expected 1 result, got {len(r)}"
        return r[0]


def build_regex_upstream(nv_dat: Dict[str, str], source: Dict[str, str], version: str) -> RegexUpstream:
    # Shared by the version-check and manifest paths to keep URL/regex definitions in sync
    file_url = source["regex_file_url"]
    file_url = file_url.replace("{{nvchecker.url}}", nv_dat["url"])
    file_url = file_url.replace("{{upstream_version}}", version)

    file_regex = source["regex_file_regex"]
    file_regex = file_regex.replace("{{upstream_version}}", version)

    return RegexUpstream(nv_dat["url"], nv_dat["regex"], file_url, file_regex)


def _version_key(v: str) -> Tuple[int, ...]:
    # Split a version into numeric segments for comparison
    return tuple(int(x) for x in re.findall(r"\d+", v))


def _version_has_file(nv_dat: Dict[str, str], source: Dict[str, str], version: str) -> bool:
    exists_re = source.get("file_exists_regex")
    if not exists_re:
        return False

    try:
        upstream = build_regex_upstream(nv_dat, source, version)
        return len(upstream.get_release_asserts_regex(exists_re)) > 0
    except Exception as e:
        # Fail closed: fetch/parse errors mean the file cannot be confirmed
        logger.warning(f"[file_exists] cannot verify version {version}: {e}")
        return False


def _find_newest_version_with_file(nv_dat: Dict[str, str], source: Dict[str, str]) -> Optional[str]:
    try:
        version_upstream = RegexUpstream(nv_dat["url"], nv_dat["regex"], nv_dat["url"], nv_dat["regex"])
        raw_versions = version_upstream.get_release_asserts()
    except Exception as e:
        logger.warning(f"[file_exists] cannot fetch version list from {nv_dat.get('url')}: {e}")
        return None

    versions = []
    for v in raw_versions:
        cleaned = str(v).strip().strip("/")
        if not cleaned or cleaned == ".." or cleaned == ".":
            continue
        versions.append(cleaned)

    # Sort newest-first by numeric segments
    versions.sort(key=_version_key, reverse=True)

    for v in versions:
        if _version_has_file(nv_dat, source, v):
            logger.info(f"[file_exists] newest version with file: {v}")
            return v

    return None


def resolve_file_exists_version(
    nv_dat: Dict[str, str],
    source: Dict[str, str],
    reported_version: str,
    old_version: str,
) -> Tuple[str, str]:
    if not source.get("file_exists_regex"):
        return reported_version, "unchanged"

    effective = reported_version

    # 1. Use the reported version if it already has the target file
    if not _version_has_file(nv_dat, source, reported_version):
        # 2. Otherwise find the newest version that has the target file
        effective = _find_newest_version_with_file(nv_dat, source)
        if effective is None:
            logger.warning(
                f"[file_exists] no version with file {source['file_exists_regex']!r} found "
                f"under {nv_dat.get('url')}"
            )
            return reported_version, "unchanged"

    # 3. Compare with the old version to decide if this is an update
    if old_version and _version_key(effective) > _version_key(old_version):
        return effective, "updated"
    return effective, "unchanged"
