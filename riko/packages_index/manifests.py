# riko/packages_index/manifests.py - 清单数据模型
"""
定义 packages-index 的数据结构
"""

import semver  # 语义化版本库

from typing import Dict, List  # 类型注解


# 数据模型：PackageVersion
class PackageVersion:
    """
    包版本数据类
    表示一个包的特定版本及其清单

    对应 packages-index 中的一个清单文件（例如：board-image/LicheeRV-Nano-Build/0.20260114.0.toml）
    """

    def __init__(self, version: semver.Version, upstream_version: str, manifest: Dict):
        """
        初始化 PackageVersion

        :param version: 语义化版本对象（semver.Version）
        :param upstream_version: 上游版本号（字符串）
        :param manifest: 清单内容（字典，包含所有配置项）
        """
        # 版本信息
        self.version: semver.Version = version  # 语义化版本（用于比较）
        self.upstream_version: str = upstream_version  # 上游版本号（原始字符串）
        self.manifest: Dict = manifest  # 清单内容（TOML 解析后的字典）

        # 策略标记
        # riko.toml 中定义的策略（如 "keep_back", "skip" 等）
        self.policies: set[str] = set()  # 使用 set 存储策略（自动去重）

    # Getter/Setter 方法
    def set_manifest(self, manifest: Dict):
        """设置清单内容"""
        self.manifest = manifest

    def get_manifest(self) -> Dict:
        """获取清单内容"""
        return self.manifest

    def get_version(self) -> semver.Version:
        """获取语义化版本对象"""
        return self.version

    def get_upstream_version(self) -> str:
        """获取上游版本号字符串"""
        return self.upstream_version

    # 策略管理
    def add_policies(self, policies: List[str]) -> None:
        """
        添加策略列表

        :param policies: 策略名称列表（例如：["keep_back", "skip"]）

        """
        for p in policies:
            self.policies.add(p)

    def accept_policy(self, policy: str) -> bool:
        """
        检查是否接受某个策略

        必须在 add_policies() 之后调用

        :param policy: 策略名称
        :return: 如果接受该策略返回 True，否则返回 False

        """
        return policy in self.policies


# 数据模型：Package（包）
class Package:
    """
    包数据类
    表示一个包的所有版本

    对应 packages-index 中的一个包目录（例如：board-image/LicheeRV-Nano-Build/）
    """

    def __init__(self, name: str, versions=None):
        """
        初始化 Package

        :param name: 包名称（例如："LicheeRV-Nano-Build"）
        :param versions: 版本列表（可选，默认为空列表）

        """
        # 声明类型注解（仅用于提示）
        self._versions: List[PackageVersion]

        # 条件初始化
        if versions is None:
            self._versions = []  # 如果为 None，创建空列表
        else:
            self._versions = versions  # 否则使用传入的列表

        self.name: str = name  # 包名称

    # 版本管理
    def add_version(self, version: PackageVersion) -> None:
        """
        添加一个版本

        :param version: PackageVersion 对象
        """
        self._versions.append(version)

    def get_versions(self) -> List[PackageVersion]:
        """
        获取所有版本

        :return: PackageVersion 对象列表
        """
        return self._versions


# 数据模型：Category（分类）
class Category:
    """
    分类数据类
    表示一个分类及其所有包

    对应 packages-index 中的一个分类目录（例如：board-image/）
    """

    def __init__(self, name: str, packages=None):
        """
        初始化 Category

        :param name: 分类名称（例如："board-image"）
        :param packages: 包字典（可选，默认为空字典）

        """
        # 声明类型注解
        self._packages: Dict[str, Package]

        # 条件初始化
        if packages is None:
            self._packages = {}  # 空字典
        else:
            self._packages = packages

        self._name: str = name  # 分类名称

    # 包管理
    def add_package(self, package: Package) -> None:
        """
        添加一个包

        :param package: Package 对象

        """
        self._packages.update({package.name: package})

    def get_package(self, name: str) -> Package | None:
        """
        根据名称获取包

        :param name: 包名称
        :return: Package 对象，如果不存在返回 None

        """
        return self._packages.get(name)

    def get_name(self) -> str:
        """获取分类名称"""
        return self._name
