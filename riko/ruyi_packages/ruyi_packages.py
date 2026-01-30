# riko/ruyi_packages/ruyi_packages.py - 上游包配置管理
"""
加载和管理 ruyi_packages 目录下的所有 riko.toml 配置文件
类似于 Java 的 Configuration Repository
"""

import logging
import os
import tomllib  # TOML 解析库（Python 3.11+ 内置）

from pathlib import Path
from typing import Dict, List  # 类型注解

logger = logging.getLogger(__name__)


# ========== 数据模型：UpstreamConfig（上游配置） ==========
class UpstreamConfig:
    """
    上游配置数据类
    表示一个 upstream 的 riko.toml 配置

    riko.toml 结构示例：
    [nvchecker]
    source = "alpm"
    alpm = "lichee-rv-nano-build"

    [source]
    ...

    [entities.image-combo]
    revyos-sg2042 = "sg2042"
    revyos-lpi4a = "lpi4a"

    [policies.revyos-sg2042]
    ...
    """

    def __init__(self, name: str, category: str, nv_dat: Dict, up_source: Dict):
        """
        初始化 UpstreamConfig

        :param name: upstream 名称（例如："LicheeRV-Nano-Build"）
        :param category: 分类（例如："board-image"）
        :param nv_dat: nvchecker 配置数据（从 riko.toml 的 [nvchecker] 部分）
        :param up_source: 额外源数据（从 riko.toml 的 [source] 部分）
        """
        # nvchecker 配置
        self._name: str = name  # upstream 名称
        self._category: str = category  # 分类
        self._nv_data: Dict = nv_dat  # nvchecker 配置

        # 额外数据
        self._source: Dict[str, str] = up_source  # 源配置
        self._combos: List[str] = []  # combo 列表（例如：["revyos-sg2042", "revyos-lpi4a"]）
        self._policies: Dict[str, List[str]] = {}  # 策略字典（combo -> 策略列表）

    # ========== Getter 方法 ==========
    def get_name(self) -> str:
        """获取 upstream 名称"""
        return self._name

    def get_category(self) -> str:
        """获取分类"""
        return self._category

    def get_nvchecker_dat(self) -> Dict:
        """获取 nvchecker 配置数据"""
        return self._nv_data

    # ========== Combo 管理 ==========
    def set_combos(self, combos: List[str], policies: Dict[str, List[str]]) -> None:
        """
        设置 board-image combos

        :param combos: combo 列表（一组相关联的板卡镜像）
                      它们从同一个源发布，应该一起检查
        :param policies: 策略字典（combo 名称 -> 策略列表）
                        例如：{"revyos-sg2042": ["keep_back"]}

        示例：
        combos = ["revyos-sg2042", "revyos-lpi4a"]
        policies = {
            "revyos-sg2042": ["keep_back"],
            "revyos-lpi4a": []
        }
        """
        self._combos = combos
        self._policies = policies

    def get_combos(self) -> List[str]:
        """获取 combo 列表"""
        return self._combos

    def get_policies(self) -> Dict[str, List[str]]:
        """获取所有策略字典"""
        return self._policies

    def get_policy(self, combo: str) -> List[str]:
        """
        获取指定 combo 的策略列表

        :param combo: combo 名称
        :return: 策略列表，如果 combo 不存在返回空列表

        Python 特殊语法：
        - .get(combo, []): 字典方法，如果键不存在返回默认值 []
        """
        return self._policies.get(combo, [])

    def get_source(self) -> Dict[str, str]:
        """获取源配置"""
        return self._source


# ========== 配置管理器：RuyiPackages ==========
class RuyiPackages:
    """
    ruyi_packages 配置管理器
    负责扫描和加载 ruyi_packages 目录下的所有 riko.toml 文件
    目前仅支持 board-image 分类

    目录结构示例：
    ruyi_packages/
    ├── board-image/
    │   ├── LicheeRV-Nano-Build/
    │   │   └── riko.toml
    │   └── armbian/
    │       └── riko.toml
    └── os-dist/
        └── ...
    """

    def __init__(self, path: Path):
        """
        初始化 RuyiPackages

        :param path: ruyi_packages 目录路径
        """
        self._path: Path = path  # ruyi_packages 目录路径
        self._upstream_cfg: Dict[str, UpstreamConfig] = {}  # upstream 配置字典（名称 -> 配置）

    # ========== 加载配置 ==========
    def load(self):
        """
        扫描并加载所有 riko.toml 文件

        目录遍历：
        1. 遍历每个分类目录（board-image, os-dist 等）
        2. 遍历每个 upstream 目录
        3. 读取 riko.toml 文件
        4. 解析配置并创建 UpstreamConfig 对象

        :raises FileNotFoundError: 如果 ruyi_packages 目录不存在

        Python 特殊语法：
        - os.listdir(): 列出目录内容（类似于 Java's File.list()）
        - with open() as f: 上下文管理器（自动关闭文件）
        - tomllib.load(f): 解析 TOML 文件（类似于 Jackson 解析 JSON）
        """
        if not self._path.exists():
            raise FileNotFoundError(self._path)

        # 遍历每个分类目录
        for cat in os.listdir(self._path):
            # 遍历每个 upstream 目录
            for pkg in os.listdir(self._path / cat):
                # 读取 riko.toml 文件
                # "rb" 模式：二进制读取模式（tomllib 要求）
                with open(self._path / cat / pkg / "riko.toml", "rb") as f:
                    cfg: Dict = tomllib.load(f)  # 解析 TOML 为字典

                # 创建 UpstreamConfig 对象
                # cfg["nvchecker"]: nvchecker 配置部分
                # cfg.get("source", {}): source 配置部分，如果不存在返回空字典
                up = UpstreamConfig(pkg, cat, cfg["nvchecker"], cfg.get("source", {}))

                # 目前仅支持 board-image 分类
                if cat != "board-image":
                    raise NotImplementedError(f"Category {cat} not implemented")

                # 解析 image-combo 列表
                com_orig = cfg["entities"]["image-combo"]  # 原始 combo 配置
                combos = []  # 过滤后的 combo 列表

                # 策略可能不存在（.get() 返回 None）
                policies: Dict[str, List[str]] | None = cfg.get("policies")

                # 过滤掉标记为 "skip" 的 combo
                # 如果 combo 的策略列表中包含 "skip"，则跳过该 combo
                for c in com_orig:
                    # isinstance() 检查类型（类似于 Java's instanceof）
                    if policies is not None and isinstance(policies.get(c), list) and "skip" in policies[c]:
                        logger.debug(f"apply `skip` policy, combo {c} skipped")
                        policies.pop(c)  # 从策略字典中移除
                        continue  # 跳过此 combo
                    combos.append(c)  # 添加到有效 combo 列表

                # 只添加至少有一个有效 combo 的 upstream
                if len(combos) > 0:
                    up.set_combos(combos, policies if policies is not None else {})
                    self._upstream_cfg[pkg] = up

    # ========== 查询方法 ==========
    def get_upstreams(self) -> Dict[str, UpstreamConfig]:
        return self._upstream_cfg

    def get_upstream(self, up_name: str) -> UpstreamConfig | None:
        return self._upstream_cfg.get(up_name)
