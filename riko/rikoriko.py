# riko/rikoriko.py - Riko 核心类
"""
Riko 是整个系统的核心协调者（类似于 Java 的 Service 层或 Facade 模式）
负责整合三个数据源：
1. PackagesIndex - packages-index 仓库的清单数据
2. RuyiPackages - ruyi_packages 目录的配置数据
3. NvcheckerResults - nvchecker 检查结果
"""

import json
import logging
import semver  # 语义化版本库（类似于 Java 的 semver 库）
import tomli_w  # TOML 写入库

from typing import Dict, List  # 类型提示（类似于 Java 的泛型）

# 导入配置常量（需要在 rikoriko 中使用的路径）
from .config.const import ruyi_cache_dir, nvchecker_config, nvchecker_result, nvchecker_old_ver, nvchecker_new_ver, \
    ruyi_pkgs_dir
from .nvchecker.results import NvcheckerResults
from .packages_index.packages_index import PackagesIndex
from .packages_index.manifests import PackageVersion
from .ruyi_packages.ruyi_packages import RuyiPackages, UpstreamConfig

logger = logging.getLogger(__name__)


class Riko:
    """
    Riko 核心类（类似于 Java 的 @Service 单例类）
    使用 Facade 模式整合多个数据源，提供统一的查询接口
    """

    # ========== 构造函数 ==========
    # Python 特殊语法：__init__() 相当于 Java 的构造函数
    # self 相当于 Java 的 this
    def __init__(self):
        # 实例变量（类似于 Java 的 private 字段）
        # 类型注解：PackagesIndex 表示变量类型（可选，不影响运行）
        self._packages_index: PackagesIndex = PackagesIndex(ruyi_cache_dir / "ruyi" / "packages-index")
        self._ruyi_packages: RuyiPackages = RuyiPackages(ruyi_pkgs_dir)
        self._nvchecker_result: NvcheckerResults = NvcheckerResults(nvchecker_result)

    # ========== 从本地缓存加载数据 ==========
    def load_from_cache(self) -> None:
        """
        从本地缓存加载所有数据源的数据
        类似于 Java 的 @PostConstruct 初始化方法
        :return: None
        """
        try:
            self._ruyi_packages.load()    # 加载 ruyi_packages 配置
            self._packages_index.load()   # 加载 packages-index 清单
            self._nvchecker_result.load() # 加载 nvchecker 检查结果
        except FileNotFoundError:
            logger.warning("Riko cache not found, please run `riko check` first")

    # ========== 生成 nvchecker 配置文件 ==========
    def generate_nvchecker_config(self) -> None:
        """
        生成 nvchecker 工具的配置文件
        从所有 upstream 的 riko.toml 中提取 nvchecker 配置
        """
        # nvchecker 配置结构（类似于 Java 的 Map<String, Object>）
        nvchecker_cfg: Dict = {
            "__config__": {
                "oldver": str(nvchecker_old_ver.name),  # 旧版本文件路径
                "newver": str(nvchecker_new_ver.name),  # 新版本文件路径
            }
        }

        # 遍历所有 upstream 包，提取 nvchecker 配置
        # .values() 返回字典的所有值（类似于 Java 的 Map.values()）
        for c in self._ruyi_packages.get_upstreams().values():
            nvchecker_cfg[c.get_name()] = c.get_nvchecker_dat()

        # Python 上下文管理器：with open() as f
        # 类似于 Java 的 try-with-resources，自动关闭文件
        # "wb" 表示二进制写入模式（类似于 Java's FileOutputStream）
        with open(nvchecker_config, "wb") as f:
            tomli_w.dump(nvchecker_cfg, f)  # 写入 TOML 格式

    # ========== 从 packages-index 生成 nvchecker 旧版本配置文件 ==========
    def generate_nvchecker_old_ver(self) -> None:
        """
        从 packages-index 读取当前版本，生成 nvchecker 的 old_ver.json
        用于 nvchecker 对比新旧版本
        :return: None
        """
        self._packages_index.load()

        nvchecker_ver = 2
        old_data = {}

        # 遍历所有 upstream 包
        for up in self._ruyi_packages.get_upstreams().values():
            name = up.get_name()
            cat = self._packages_index.get_category(up.get_category())

            # 在所有 combos 中找到最新版本
            # semver.Version(0, 0, 0) 创建版本对象 0.0.0（最小版本）
            version = semver.Version(0, 0, 0)
            upstream_version = ""

            for pkg in up.get_combos():
                ver = self.get_packages_index_latest(cat.get_name(), pkg)
                # compare() > 0 表示 ver 比 version 更新
                if ver.version.compare(version) > 0:
                    version = ver.version
                    upstream_version = ver.upstream_version

            old_data[name] = {"version": upstream_version}

        # 格式化为 nvchecker 需要的 JSON 结构
        format_data = {
            "version": nvchecker_ver,
            "data": old_data,
        }

        # 写入 JSON 文件（"w" 表示文本写入模式）
        with open(nvchecker_old_ver, "w") as f:
            json.dump(format_data, f, indent=2)  # indent=2 美化格式（2 空格缩进）

    # ========== 查询方法：获取 nvchecker 结果 ==========
    def get_nvchecker_results(self, event_or_level: str) -> List[Dict]:
        """
        获取 nvchecker 检查结果
        :param event_or_level: 事件类型或日志级别（"updated", "up-to-date", "error" 等）
        :return: 结果字典列表
        """
        if event_or_level == "any":
            return self._nvchecker_result.get_data()
        else:
            return self._nvchecker_result.get_event_data(event_or_level)

    # ========== 查询方法：获取指定上游的 nvchecker 结果 ==========
    def get_nvchecker_result(self, up_name: str) -> Dict | None:
        """
        根据上游名称查找 nvchecker 结果
        :param up_name: 上游包名称
        :return: 结果字典，未找到返回 None
        """
        for r in self._nvchecker_result.get_data():
            if r.get("name") == up_name:
                return r

        return None

    # ========== Getter 方法（类似于 Java 的 getter） ==========
    def get_packages_index(self) -> PackagesIndex:
        """获取 packages-index 数据源"""
        return self._packages_index

    # ========== 查询方法：获取 packages-index 中的最新版本 ==========
    def get_packages_index_latest(self, category: str, pkg: str) -> PackageVersion:
        """
        获取指定包的最新版本
        :param category: 分类（例如："board-image"）
        :param pkg: 包名（例如："LicheeRV-Nano-Build"）
        :return: 最新版本的 PackageVersion 对象
        """
        version = semver.Version(0, 0, 0)  # 初始化为最小版本
        package_version = None

        # 遍历该包的所有版本
        for v in self._packages_index.get_category(category).get_package(pkg).get_versions():
            if v.version.compare(version) > 0:
                # 跳过空版本
                if v.upstream_version is None or v.upstream_version == "":
                    continue
                version = v.version
                package_version = v

        # 递归调用获取完整的清单信息
        return self.get_packages_index_manifest(category, pkg, package_version.upstream_version)

    # ========== 查询方法：获取指定版本的清单 ==========
    def get_packages_index_manifest(self, category: str, pkg: str, up_ver: str) -> PackageVersion | None:
        """
        获取指定包的指定版本的清单
        :param category: 分类
        :param pkg: 包名
        :param up_ver: 上游版本号
        :return: PackageVersion 对象，未找到返回 None
        """
        for v in self._packages_index.get_category(category).get_package(pkg).get_versions():
            if v.upstream_version == up_ver:
                return v

        return None

    # ========== Getter 方法 ==========
    def get_ruyi_packages(self) -> RuyiPackages:
        """获取 ruyi-packages 数据源"""
        return self._ruyi_packages

    # ========== 查询方法：获取指定上游的配置 ==========
    def get_ruyi_package(self, up_name: str) -> UpstreamConfig | None:
        """
        根据上游名称获取 riko.toml 配置
        :param up_name: 上游包名称
        :return: UpstreamConfig 对象，未找到返回 None
        """
        return self._ruyi_packages.get_upstream(up_name)


# ========== 单例模式实现 ==========
# Python 模块级变量（类似于 Java 的 static 字段）
_myriko: Riko | None = None


def get_riko() -> Riko:
    """
    获取 Riko 单例实例（类似于 Java 的 Singleton Pattern）
    使用 global 声明修改全局变量

    Python 特殊语法：
    - global _myriko: 声明使用模块级变量（而非创建局部变量）
    - 类似于 Java 的 static 访问

    :return: Riko 单例实例
    """
    global _myriko  # 声明使用全局变量

    if _myriko is None:
        _myriko = Riko()  # 懒加载（类似于 Java 的 Lazy Initialization）

    return _myriko
