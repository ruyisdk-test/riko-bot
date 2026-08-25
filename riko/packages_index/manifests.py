import semver

from typing import Dict, List


class PackageVersion:

    def __init__(self, version: semver.Version, upstream_version: str, manifest: Dict):
        self.version: semver.Version = version
        self.upstream_version: str = upstream_version
        self.manifest: Dict = manifest

        self.policies: set[str] = set()

    def set_manifest(self, manifest: Dict):
        self.manifest = manifest

    def get_manifest(self) -> Dict:
        return self.manifest

    def get_version(self) -> semver.Version:
        return self.version

    def get_upstream_version(self) -> str:
        return self.upstream_version

    def add_policies(self, policies: List[str]) -> None:
        for p in policies:
            self.policies.add(p)

    def accept_policy(self, policy: str) -> bool:
        return policy in self.policies


class Package:

    def __init__(self, name: str, versions=None):
        self._versions: List[PackageVersion]

        if versions is None:
            self._versions = []
        else:
            self._versions = versions

        self.name: str = name

    def add_version(self, version: PackageVersion) -> None:
        self._versions.append(version)

    def get_versions(self) -> List[PackageVersion]:
        return self._versions


class Category:

    def __init__(self, name: str, packages=None):
        self._packages: Dict[str, Package]

        if packages is None:
            self._packages = {}
        else:
            self._packages = packages

        self._name: str = name

    def add_package(self, package: Package) -> None:
        self._packages.update({package.name: package})

    def get_package(self, name: str) -> Package | None:
        return self._packages.get(name)

    def get_name(self) -> str:
        return self._name
