import semver

from typing import Dict, Tuple, Union

from ..packages_index.manifests import PackageVersion
from ..upstreams.github import GithubUpstream
from ..upstreams.regex import RegexUpstream

__all__ = ("GithubUpstream", "RegexUpstream", "RikoPkg")

# upstream source type alias
_UpstreamLike = Union[GithubUpstream, RegexUpstream]


class RikoPkg(PackageVersion):

    def __init__(self, category: str, combo: str, up_name: str,
                 version: semver.Version, upstream_version: str,
                 upstream: _UpstreamLike = None) -> None:
        super().__init__(version, upstream_version, {})

        self._category: str = category
        self._combo: str = combo
        self._upstream_name: str = up_name

        self._upstream: _UpstreamLike = upstream

        self._manifest_ready: bool = False

    def set_manifest(self, manifest: Dict) -> None:
        super().set_manifest(manifest)

    def set_manifest_ready(self) -> None:
        self._manifest_ready = True

    def set_manifest_not_ready(self) -> None:
        self._manifest_ready = False

    def get_manifest_ready(self) -> bool:
        return self._manifest_ready

    def get_category(self) -> str:
        return self._category

    def get_combo(self) -> str:
        return self._combo

    def get_manifest(self) -> Tuple[Dict, bool]:
        return super().get_manifest(), self._manifest_ready

    def get_version(self) -> semver.Version:
        return super().get_version()

    def get_upstream_version(self) -> str:
        return super().get_upstream_version()

    def get_upstream(self) -> _UpstreamLike | None:
        return self._upstream

    def get_upstream_name(self) -> str:
        return self._upstream_name
