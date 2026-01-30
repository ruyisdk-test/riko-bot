# riko/rikoriko.py - Riko 核心类

import json
import logging
import semver
import tomli_w

from typing import Dict, List

# 导入配置常量（需要在 rikoriko 中使用的路径）
from .config.const import ruyi_cache_dir, nvchecker_config, nvchecker_result, nvchecker_old_ver, nvchecker_new_ver, \
    ruyi_pkgs_dir
from .nvchecker.results import NvcheckerResults
from .packages_index.packages_index import PackagesIndex
from .packages_index.manifests import PackageVersion
from .ruyi_packages.ruyi_packages import RuyiPackages, UpstreamConfig

logger = logging.getLogger(__name__)


class Riko:

    def __init__(self):
        self._packages_index: PackagesIndex = PackagesIndex(ruyi_cache_dir / "ruyi" / "packages-index")
        self._ruyi_packages: RuyiPackages = RuyiPackages(ruyi_pkgs_dir)
        self._nvchecker_result: NvcheckerResults = NvcheckerResults(nvchecker_result)

    def load_from_cache(self) -> None:
        try:
            self._ruyi_packages.load()    # 加载 ruyi_packages 配置
            self._packages_index.load()   # 加载 packages-index 清单
            self._nvchecker_result.load() # 加载 nvchecker 检查结果
        except FileNotFoundError:
            logger.warning("Riko cache not found, please run `riko check` first")

    def generate_nvchecker_config(self) -> None:
        nvchecker_cfg: Dict = {
            "__config__": {
                "oldver": str(nvchecker_old_ver.name),
                "newver": str(nvchecker_new_ver.name),
            }
        }

        for c in self._ruyi_packages.get_upstreams().values():
            nvchecker_cfg[c.get_name()] = c.get_nvchecker_dat()

        with open(nvchecker_config, "wb") as f:
            tomli_w.dump(nvchecker_cfg, f)

    def generate_nvchecker_old_ver(self) -> None:
        self._packages_index.load()

        nvchecker_ver = 2
        old_data = {}

        for up in self._ruyi_packages.get_upstreams().values():
            name = up.get_name()
            cat = self._packages_index.get_category(up.get_category())

            version = semver.Version(0, 0, 0)
            upstream_version = ""

            for pkg in up.get_combos():
                ver = self.get_packages_index_latest(cat.get_name(), pkg)
                if ver.version.compare(version) > 0:
                    version = ver.version
                    upstream_version = ver.upstream_version

            old_data[name] = {"version": upstream_version}

        format_data = {
            "version": nvchecker_ver,
            "data": old_data,
        }

        with open(nvchecker_old_ver, "w") as f:
            json.dump(format_data, f, indent=2)

    def get_nvchecker_results(self, event_or_level: str) -> List[Dict]:
        if event_or_level == "any":
            return self._nvchecker_result.get_data()
        else:
            return self._nvchecker_result.get_event_data(event_or_level)

    def get_nvchecker_result(self, up_name: str) -> Dict | None:
        for r in self._nvchecker_result.get_data():
            if r.get("name") == up_name:
                return r

        return None

    def get_packages_index(self) -> PackagesIndex:
        return self._packages_index

    def get_packages_index_latest(self, category: str, pkg: str) -> PackageVersion:
        version = semver.Version(0, 0, 0)
        package_version = None

        for v in self._packages_index.get_category(category).get_package(pkg).get_versions():
            if v.version.compare(version) > 0:
                if v.upstream_version is None or v.upstream_version == "":
                    continue
                version = v.version
                package_version = v

        return self.get_packages_index_manifest(category, pkg, package_version.upstream_version)

    def get_packages_index_manifest(self, category: str, pkg: str, up_ver: str) -> PackageVersion | None:
        for v in self._packages_index.get_category(category).get_package(pkg).get_versions():
            if v.upstream_version == up_ver:
                return v

        return None

    def get_ruyi_packages(self) -> RuyiPackages:
        return self._ruyi_packages

    def get_ruyi_package(self, up_name: str) -> UpstreamConfig | None:
        return self._ruyi_packages.get_upstream(up_name)


_myriko: Riko | None = None


def get_riko() -> Riko:
    global _myriko

    if _myriko is None:
        _myriko = Riko()

    return _myriko
