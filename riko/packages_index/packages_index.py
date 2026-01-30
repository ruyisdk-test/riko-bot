# riko/packages_index/packages_index.py - packages-index 仓库数据加载
"""
加载和解析 packages-index 仓库的清单文件
构建三层结构：Category → Package → PackageVersion

类似于 Java 的 Repository + Entity Loader
"""

import os
import semver  # 语义化版本库
import tomllib  # TOML 解析库

from pathlib import Path
from typing import Dict, List

# 导入数据模型类
from .manifests import Category, Package, PackageVersion


class PackagesIndex:
    """
    packages-index 仓库数据加载器
    负责扫描 manifests/ 目录并加载所有清单文件

    目录结构示例：
    packages-index/
    └── manifests/
        ├── board-image/
        │   ├── LicheeRV-Nano-Build/
        │   │   ├── 0.20260114.0.toml
        │   │   └── 0.20260107.0.toml
        │   └── armbian/
        │       └── 23.11.0-trunk.20250120.toml
        └── os-dist/
            └── ...
    """

    def __init__(self, path: Path):
        """
        初始化 PackagesIndex

        :param path: packages-index 仓库根目录
        """
        self._path: Path = path  # 仓库路径
        self._categories: Dict[str, Category] = {}  # 分类字典（名称 -> Category 对象）

    # ========== 加载清单数据 ==========
    def load(self) -> None:
        """
        扫描并加载所有清单文件

        加载流程：
        1. 遍历 manifests/ 下的每个分类目录
        2. 遍历每个分类下的包目录
        3. 遍历每个包下的版本文件（.toml）
        4. 解析 TOML 文件并创建数据对象

        :raises FileNotFoundError: 如果 manifests 目录不存在

        Python 特殊语法：
        - os.listdir(): 列出目录内容
        - .suffix: 文件扩展名（例如：".toml"）
        - .stem: 文件名（不含扩展名，例如："0.20260114.0"）
        - .read_text(): 读取文本内容
        """
        # 检查 manifests 目录是否存在
        if not os.path.exists(self._path / 'manifests'):
            raise FileNotFoundError(self._path / 'manifests')

        # 遍历每个分类目录（例如：board-image, os-dist）
        for cat in os.listdir(self._path / 'manifests'):
            mycat = Category(cat)  # 创建 Category 对象

            # 遍历该分类下的每个包（例如：LicheeRV-Nano-Build, armbian）
            for pkg in os.listdir(self._path / 'manifests' / cat):
                mypkg = Package(pkg)  # 创建 Package 对象

                # 遍历该包下的每个版本文件
                for ver in os.listdir(self._path / 'manifests' / cat / pkg):
                    tml = self._path / 'manifests' / cat / pkg / ver  # 完整文件路径

                    # 检查文件类型（仅支持 .toml）
                    # .suffix: 文件扩展名（例如：".toml"）
                    # .lower(): 转换为小写（处理 ".TOML" 等情况）
                    if tml.suffix.lower() != '.toml':
                        raise NotImplementedError(f"file type {tml.suffix.lower()} not supported")

                    # 解析 TOML 文件
                    # .read_text(): 读取文件全部文本（类似于 Java's Files.readString()）
                    # tomllib.loads(): 从字符串解析 TOML（类似于 Jackson 解析 JSON）
                    data = tomllib.loads(tml.read_text())

                    # 解析版本号
                    # tml.stem: 文件名（不含扩展名），例如："0.20260114.0"
                    # semver.Version.parse(): 解析语义化版本（类似于 Java's semver 库）
                    version = semver.Version.parse(tml.stem)

                    # 获取 upstream_version（从 metadata 部分）
                    # .get() 链式访问：data.get('metadata').get('upstream_version')
                    # 如果 metadata 不存在或 upstream_version 不存在，会抛出 AttributeError
                    upstream_version = data.get('metadata').get('upstream_version')

                    # 创建 PackageVersion 对象并添加到包中
                    mypkg.add_version(PackageVersion(version, upstream_version, data))

                # 将包添加到分类中
                mycat.add_package(mypkg)

            # 将分类添加到字典中
            self._categories.update({cat: mycat})

    # ========== 查询方法 ==========
    def get_category(self, name: str) -> Category | None:
        """
        根据名称获取分类

        :param name: 分类名称（例如："board-image"）
        :return: Category 对象，如果不存在返回 None

        Python 特殊语法：
        - .get(name): 字典方法（类似于 Java's Map.get()）
        - Category | None: 联合类型注解（Python 3.10+）
        """
        return self._categories.get(name)
