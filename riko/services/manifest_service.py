# riko/services/manifest_service.py - 清单生成服务


import ast
import copy
import hashlib
import importlib.util
import logging
import os
import re
import semver
import subprocess
import tomli_w
import traceback
import yaml

from typing import Callable, Dict, List, Tuple

from ..interfaces.cli.utils import ensure_dir
from ..core.models import RikoPkg
from ..config.const import riko_cache_dir, riko_manifests_dir, ruyi_pkgs_dir
from ..packages_index.manifests import PackageVersion
from ..core import get_riko
from ..upstreams.github import GithubUpstream
from ..upstreams.regex import RegexUpstream
# 数据库记录工具
from ..database import record_command  # 数据库记录装饰器
from ..database import get_recorder  # 数据库记录器

logger = logging.getLogger(__name__)


class ManifestService:
    """清单生成服务类"""

    @staticmethod
    @record_command("manifests")
    def generate(up_name: str, gen_vers: List[str], down_grade: bool):
        """
        生成清单文件的主函数

        1. 获取 nvchecker 检查结果，确定版本更新情况
        2. 确定要生成的版本列表
        3. 加载 riko.toml 配置文件
        4. 加载旧的 packages-index manifest 作为基础
        5. 解析并执行 riko.yaml 模板
        6. 执行自定义的 rikoring 和 post_rikoring 钩子
        7. 验证并保存生成的 manifest 文件
        """

        recorder = get_recorder()

        # 1 获取 nvchecker 结果
        # nvchecker 是一个版本检查工具，用于检测上游软件的版本更新
        result = get_riko().get_nvchecker_result(up_name)
        # 返回格式示例:
        # {
        #     "name": "LicheeRV-Nano-Build",
        #     "event": "updated",           # 事件类型: updated(有更新) 或 unchanged(无更新)
        #     "old_version": "0.20260107.0", # 旧版本
        #     "version": "0.20260114.0"      # 新版本
        # }

        # 如果没有找到 nvchecker 记录，可能是新包
        if result is None:
            logger.error("No such nvchecker upstream %s", up_name)
            logger.error("May be new package")
        else:
            # 如果用户没有指定要生成的版本，使用 nvchecker 检测到的版本
            if len(gen_vers) == 0:
                gen_vers.append(result["version"])

        # 2 确定旧版本和新版本
        if result is None:
            # 如果是新包，使用空字符串作为旧版本的标志
            # TODO: 后续可以设计更好的版本基准支持机制
            old_ver = ""
        elif result["event"] == "updated":
            # 如果有更新，记录旧版本
            old_ver = result["old_version"]
        else:
            # 如果没有更新且不允许降级，则直接返回
            old_ver = result["version"]
            if not down_grade:
                logger.warning("Already updated")
                return

        # 3 清理版本列表
        # 从生成列表中移除旧版本（避免重复生成）
        if old_ver in gen_vers:
            logger.warning(f"Remove old version `{old_ver}` from generate version list")
            gen_vers.remove(old_ver)

        # 检查是否还有版本需要生成
        if len(gen_vers) == 0:
            logger.warning("No version to be generated")
            return

        logger.info(f"Generate {up_name} manifests for versions {gen_vers}")

        # 4 加载 riko.toml 配置
        # riko.toml 包含了包的基本配置信息，如 upstream 来源、combos 等
        riko_toml = get_riko().get_ruyi_package(up_name)
        if riko_toml is None:
            raise FileNotFoundError(f"No riko upstream package `{up_name}` found")

        # 5 加载旧的 packages-index manifest
        # packages-index 是包索引数据库，存储了历史版本的 manifest 信息
        # 这些旧版本将作为生成新版本的基础模板
        gen_cbs: List[str] = riko_toml.get_combos()  # 获取所有的 combo 组合
        gen_cbs_ov: List[PackageVersion] = []  # 存储每个 combo 对应的旧版本

        for c in gen_cbs:
            if old_ver:
                # 尝试获取旧版本的 manifest
                pkg_ver = get_riko().get_packages_index_manifest(riko_toml.get_category(), c, old_ver)
                if pkg_ver is None:
                    # 如果找不到旧版本的 manifest，检查是否有 keep_back 策略
                    if "keep_back" in riko_toml.get_policy(c):
                        # keep_back 策略: 使用最新的 manifest 作为基础
                        pkg_ver = get_riko().get_packages_index_latest(riko_toml.get_category(), c)
                        if pkg_ver is not None:
                            pkg_ver.add_policies(riko_toml.get_policy(c))
                            logger.debug(f"no ruyi packages-index manifest for category `{riko_toml.get_category()}` "
                                         f"package {c} version {old_ver} found")
                            logger.debug(f"use `keep_back` policy, find ruyi packages-index manifest of category "
                                         f"`{riko_toml.get_category()}` package {c} version {pkg_ver.upstream_version}")
                            logger.info(f"{up_name} manifest {c} combo base on old version `{pkg_ver.upstream_version}`")
                        else:
                            logger.info(f"No ruyi packages-index manifest for category `{riko_toml.get_category()}` "
                                        f"package {c} version {old_ver} found, and no latest version found")
                            logger.info(f"Use placeholder version 0.0.0 for {c}")
                            pkg_ver = PackageVersion(semver.Version.parse("0.0.0"), "0.0.0", {})
                    else:
                        logger.info(f"No ruyi packages-index manifest for category `{riko_toml.get_category()}` "
                                    f"package {c} version {old_ver} found")
                        logger.info(f"Use placeholder version 0.0.0 for {c}")
                        pkg_ver = PackageVersion(semver.Version.parse("0.0.0"), "0.0.0", {})
                gen_cbs_ov.append(pkg_ver)
            else:
                # 对于新包，使用 0.0.0 作为占位版本
                # TODO: 后续需要设计更完善的版本基准支持机制:
                # TODO: * 设计手动维护的 toml 列表
                # TODO: * 设计忽略的上游版本列表
                gen_cbs_ov.append(PackageVersion(semver.Version.parse("0.0.0"), "0.0.0", {}))

        # 6 准备输出目录
        ensure_dir(riko_cache_dir)      # 缓存目录，用于存储下载的文件
        ensure_dir(riko_manifests_dir)  # manifest 输出目录

        # 定位 riko.py 和 riko.yaml 文件
        riko_py_p = ruyi_pkgs_dir / riko_toml.get_category() / up_name / "riko.py"
        riko_yaml_p = ruyi_pkgs_dir / riko_toml.get_category() / up_name / "riko.yaml"

        # riko.yaml 是必需的模板文件
        if not riko_yaml_p.exists():
            logger.fatal("You must use riko.yaml in this riko version")
            return

        # 加载 riko.yaml 模板
        riko_yaml_orig: Dict = yaml.safe_load(riko_yaml_p.read_text())
        assert riko_yaml_orig["format"] == "v1"

        # 7 定义 riko.yaml 解析函数
        # 这些函数用于解析和处理 riko.yaml 模板中的表达式

        def tree_parse_inner(key: str, value: Dict | List | str) -> Dict:
            """
            递归解析 riko.yaml 树形结构
            - 将字符串表达式解析为 AST (Abstract Syntax Tree)
            - 保留普通字符串不变
            """
            if isinstance(value, Dict):
                tree_new = {}
                for k, v in value.items():
                    tree_new.update(tree_parse_inner(k, v))

                return {key: tree_new}
            elif isinstance(value, List):
                list_new = []
                if isinstance(value[0], Dict):
                    for v in value:
                        list_new.append(tree_parse_inner("k", v)["k"])
                elif isinstance(value[0], str):
                    for s in value:
                        list_new.append(tree_parse_inner("k", s)["k"])
                else:
                    raise RuntimeError(f"Unexpected type {type(value)}")
                return {key: list_new}
            elif isinstance(value, str):
                # 保留纯字母数字字符串不变
                if re.match(r"^[a-zA-Z0-9 ,\-+.]+$", value):
                    return {key: value}
                # 将其他字符串解析为表达式 AST
                return {key: ast.parse(value, mode="eval")}
            elif value is None:
                return {key: ""}
            else:
                raise RuntimeError(f"Unexpected type {type(value)}")

        def tree_update_inner(tree_old: Dict, tree_up: Dict) -> None:
            """
            递归更新树形结构，合并旧的配置和新的配置
            """
            for k in tree_up.keys():
                if k in tree_old.keys() and isinstance(tree_old[k], Dict) and isinstance(tree_up[k], Dict):
                    # 保留旧字典中的键
                    tree_update_inner(tree_old[k], tree_up[k])
                else:
                    tree_old[k] = tree_up[k]

        def tree_update(tree_old: Dict, tree_raw: Dict) -> Dict:
            """
            合并两个树形配置，返回新的配置
            用于将 combo 特定的配置合并到基础配置中
            """
            tree_new = copy.deepcopy(tree_old)

            tree_update_inner(tree_new, tree_parse_inner("k", tree_raw)["k"])

            return tree_new

        # 8 定义 AST 检查函数
        # 用于安全性检查，确保 riko.yaml 中的表达式只使用允许的操作

        def riko_yaml_ast_check(exp: ast.Expression, g_vars: Dict, g_calls: Dict) -> bool:
            """
            检查 AST 表达式的安全性
            确保只使用允许的 AST 节点类型
            """
            _ast_allowed = (ast.Expression, ast.Call, ast.Name, ast.Load, ast.Constant, ast.Tuple)
            # TODO: 实现完整的 AST 检查逻辑
            return True

        # 9 定义 riko.yaml 运行函数
        # 这个函数负责执行 riko.yaml 中的动态表达式，生成最终的 manifest

        def riko_yaml_run(_up, _ov: semver.Version, nm: Dict, ym: Dict) -> Dict:
            """
            执行 riko.yaml 模板，生成 manifest

            参数:
                _up: upstream 对象 (GithubUpstream 或 RegexUpstream)
                _ov: 旧版本号
                nm: 新 manifest 的元数据
                ym: riko.yaml 解析后的配置树

            返回:
                生成的 manifest 字典
            """

            # 9.1 初始化运行时变量
            _upstream_version = nm["metadata"]["upstream_version"]
            _files = {}   # 存储文件信息
            _label = []   # 用于追踪当前处理的位置（栈）

            # 9.2 定义 riko.yaml 工具函数
            # 这些函数可以在 riko.yaml 表达式中调用

            def _file(_name_url: Tuple[str, str]) -> str:
                """注册文件信息，返回文件名"""
                if _name_url[0] not in _files.keys():
                    _files[_name_url[0]] = {}

                _files[_name_url[0]]["url"] = _name_url[1]
                return _name_url[0]

            def _uncompress(_orig: str) -> str:
                """
                去除压缩文件扩展名，返回解压后的文件名
                例如: "archive.tar.gz" -> "archive"
                """
                _tars = [".tar.gz", ".tar.bz2", ".tar.lz4", ".tar.xz", ".tar.zst", ".gz", ".bz2", ".lz4", ".xz", ".zst", ".zip"]
                # TODO: 使用 `tar --list` 命令获取准确的解压后文件名
                for t in _tars:
                    if _orig.endswith(t):
                        return _orig[:-len(t)]
                return _orig

            def _map_and_uncompress(_name: str, _map: str):
                """
                设置文件的映射类型和解压名称
                _map 可以是: titan, live, disk, root, boot, uboot 等
                """
                if _name not in _files.keys():
                    _files[_name] = {}

                _files[_name]["map"] = _map
                _files[_name]["uncompressed"] = _uncompress(_name)

            # 9.3 定义 riko.yaml API 函数
            # 这些函数可在 riko.yaml 表达式中使用

            def _version(major=None, minor=None, patch=None) -> str:
                """
                版本号操作函数
                可以修改版本号的 major, minor, patch 部分
                例如: _version(major=1) -> "1.0.0"
                """
                _nv = _ov
                if major is not None:
                    _nv = _nv.replace(major=major)
                if minor is not None:
                    _nv = _nv.replace(minor=minor)
                if patch is not None:
                    _nv = _nv.replace(patch=patch)

                return str(_nv)

            def _assign(_parm) -> str:
                """直接赋值，转换为字符串"""
                return str(_parm)

            def _substring(_sub: str) -> Tuple[str, str]:
                """
                从 upstream 发布资产中提取子字符串
                用于根据子字符串匹配获取下载 URL
                """
                if _label[-1] == "name" and _label[-2] == "distfiles":
                    if isinstance(_up, GithubUpstream):
                        return _up.get_release_assert_substring(_sub)
                    elif isinstance(_up, RegexUpstream):
                        return _up.get_release_assert_substring(_sub)
                    else:
                        raise NotImplementedError(f"upstream source {_up.source} not supported")
                else:
                    raise NotImplementedError(f"substream not implemented for _label {_label}")

            def _regex(_pat: str) -> Tuple[str, str]:
                """
                使用正则表达式从 upstream 发布资产中匹配
                用于根据正则表达式匹配获取下载 URL
                """
                if _label[-1] == "name" and _label[-2] == "distfiles":
                    if isinstance(_up, GithubUpstream):
                        return _up.get_release_assert_regex(_pat)
                    elif isinstance(_up, RegexUpstream):
                        return _up.get_release_assert_regex(_pat)
                    else:
                        raise NotImplementedError(f"upstream source {_up.source} not supported")
                else:
                    raise NotImplementedError(f"substream not implemented for _label {_label}")

            # 以下是不同分区类型的文件处理函数
            def _titan(_name_url: Tuple[str, str]) -> str:
                """处理 titan 分区类型 (Spacemit K1 平台)"""
                _map_and_uncompress(_name_url[0], "titan")
                return _file(_name_url)

            def _live(_name_url: Tuple[str, str]) -> str:
                """处理 live 分区类型 (直接 dd 写入的完整镜像)"""
                _map_and_uncompress(_name_url[0], "live")
                return _file(_name_url)

            def _disk(_name_url: Tuple[str, str]) -> str:
                """处理 disk 分区类型 (完整磁盘镜像)"""
                _map_and_uncompress(_name_url[0], "disk")
                return _file(_name_url)

            def _root(_name_url: Tuple[str, str]) -> str:
                """处理 root 分区类型 (根文件系统)"""
                _map_and_uncompress(_name_url[0], "root")
                return _file(_name_url)

            def _boot(_name_url: Tuple[str, str]) -> str:
                """处理 boot 分区类型 (引导分区)"""
                _map_and_uncompress(_name_url[0], "boot")
                return _file(_name_url)

            def _uboot(_name_url: Tuple[str, str]) -> str:
                """处理 uboot 分区类型 (U-Boot 引导加载器)"""
                _map_and_uncompress(_name_url[0], "uboot")
                return _file(_name_url)

            #  9.4 定义 AST 运行器
            # 广度优先遍历配置树，执行其中的表达式

            def _ast_run(_ym_t: Dict):
                """
                递归遍历配置树，执行其中的 AST 表达式
                使用 BFS (广度优先搜索) 遍历
                """
                for k, v in _ym_t.items():
                    _label.append(k)  # 记录当前处理位置

                    if isinstance(v, ast.Expression):
                        # 准备全局变量和可调用函数
                        _g_vars = {"upstream_version": _upstream_version,}
                        _g_calls = {"assign": _assign,
                                    "version": _version,
                                    "substring": _substring,
                                    "regex": _regex,
                                    "titan": _titan,
                                    "live": _live,
                                    "disk": _disk,
                                    "root": _root,
                                    "boot": _boot,
                                    "uboot": _uboot,}
                        # 检查并执行表达式
                        if riko_yaml_ast_check(v, _g_vars, _g_calls):
                            _ym_t[k] = eval(compile(v, filename="<expr>", mode="eval"), _g_vars | _g_calls)
                            if not isinstance(_ym_t[k], str):
                                _ym_t[k] = f"value not str but {type(_ym_t[k])}"
                        else:
                            _ym_t[k] = "AST check failed"
                    elif isinstance(v, str):
                        pass  # 普通字符串，保持不变
                    elif isinstance(v, Dict):
                        _ast_run(v)  # 递归处理字典
                    elif isinstance(v, List):
                        for d in v:
                            _ast_run(d)  # 递归处理列表元素
                    else:
                        raise RuntimeError(f"Unexpected type {type(v)}")

                    _label.pop()  # 恢复位置

            # 9.5 执行 AST 表达式
            _ast_run(ym)

            # 9.6 填充分文件信息到 manifest
            # 确保 provisionable 字段存在
            if "provisionable" not in ym.keys():
                ym["provisionable"] = {"partition_map": {}}

            # 将文件 URL 和分区映射信息填入 manifest
            for ff in ym["distfiles"]:
                ff["urls"] = [_files[ff["name"]]["url"]]
                ym["provisionable"]["partition_map"][_files[ff["name"]]["map"]] = _files[ff["name"]]["uncompressed"]

            # 填入上游版本信息
            ym["metadata"]["upstream_version"] = _upstream_version

            return ym

        # 10 定义 manifest 推理规则
        # 使用推理规则系统自动填充 manifest 的缺失信息

        def manifests_r1(_facts: Dict) -> bool:
            """
            推理规则 R1: 根据分区映射推断 provisionable 策略

            这条规则根据 partition_map 中的分区类型，自动推断出合适的部署策略：
            - disk/live 分区 -> dd-v1 策略（直接 dd 写入）
            - uboot 分区 -> fastboot-v1(lpi4a-uboot) 策略
            - titan 分区 -> spacemit-k1-v1 策略（Spacemit K1 平台）
            - boot + root 分区 -> fastboot-v1 策略
            """
            if "provisionable" not in _facts.keys():
                return False

            _map = _facts.get("provisionable")
            if _map is None or "partition_map" not in _map.keys() or "strategy" in _map.keys():
                return False

            _map: Dict = _map["partition_map"]
            _strategy = ""

            # 根据分区类型推断策略
            if len(_map) == 1:
                if "disk" in _map.keys() or "live" in _map.keys():
                    _strategy = "dd-v1"
                elif "uboot" in _map.keys():
                    _strategy = "fastboot-v1(lpi4a-uboot)"
                elif "titan" in _map.keys():
                    _strategy = "spacemit-k1-v1"
                    # 为 Spacemit K1 添加额外的分区映射
                    _map.update({"gpt": "partition_universal.json",
                                 "bootinfo": "factory/bootinfo_sd.bin",
                                 "fsbl": "factory/FSBL.bin",
                                 "env": "env.bin",
                                 "opensbi": "fw_dynamic.itb",
                                 "uboot": "u-boot.itb",
                                 "bootfs": "bootfs.ext4",
                                 "rootfs": "rootfs.ext4"})
                    _map.pop("titan")
            elif len(_map) == 2:
                if "boot" in _map.keys() and "root" in _map.keys():
                    _strategy = "fastboot-v1"

            if _strategy != "":
                _facts["provisionable"]["strategy"] = _strategy
                return True

            return False

        def manifests_r5(_facts: Dict) -> bool:
            """
            推理规则 R5: 填充 blob.distfiles 信息

            这条规则根据部署策略，将需要的 distfiles 名称添加到 blob.distfiles 中
            blob 用于指定哪些文件需要被 blob 存储（用于大文件优化）
            """
            if "blob" not in _facts.keys():
                _facts["blob"] = {}
            _blob = _facts.get("blob")
            if "distfiles" in _blob.keys():
                return False

            if "provisionable" not in _facts.keys():
                return False

            _map = _facts.get("provisionable")
            if _map is None or "partition_map" not in _map.keys() or "strategy" not in _map.keys():
                return False

            _strategy = _facts["provisionable"]["strategy"]
            _distfiles = []

            # 根据策略收集需要的 distfiles
            if _strategy in ["dd-v1", "fastboot-v1(lpi4a-uboot)", "fastboot-v1", "spacemit-k1-v1"]:
                for _f in _facts["distfiles"]:
                    _distfiles.append(_f["name"])

            if len(_distfiles) > 0:
                _facts["blob"]["distfiles"] = _distfiles
                return True

            return False

        def manifests_r9(_facts: Dict) -> bool:
            """
            推理规则 R9: 下载文件并计算校验和

            1. 下载所有 distfiles
            2. 计算文件大小
            3. 计算 SHA256 和 SHA512 校验和
            """
            if "distfiles" not in _facts.keys():
                return False
            if not isinstance(_facts["distfiles"], List) or len(_facts["distfiles"]) == 0:
                return False

            _sizes = []
            _sha256sums = []
            _sha512sums = []

            for _d in _facts["distfiles"]:
                # 如果已有校验和信息，跳过
                if "checksums" in _d.keys() or "size" in _d.keys():
                    continue

                _url: str = _d["urls"][0]
                _f_loc = riko_cache_dir / _d["name"]

                # 下载文件
                # TODO: 使用更高级的下载库替代 curl
                _cmd: List[str] = ["curl", "-C", "-", "--retry", "3", "--retry-delay", "2", "--retry-all-errors",
                                  "-L", _url, "-o", str(_f_loc), ]
                _env = os.environ.copy()

                if _f_loc.exists():
                    _f_loc.unlink()

                _process = subprocess.Popen(_cmd, env=_env)
                _ret = _process.wait()
                if _ret != 0:
                    raise subprocess.CalledProcessError(_ret, _cmd)

                # 获取文件大小并计算哈希值
                _sizes.append(os.path.getsize(_f_loc))

                _sha256 = hashlib.sha256()
                _sha512 = hashlib.sha512()

                try:
                    with open(_f_loc, "rb") as _f:
                        while True:
                            _c = _f.read(4 * 1024)
                            if not _c:
                                break

                            _sha256.update(_c)
                            _sha512.update(_c)

                    _sha256sums.append(_sha256.hexdigest())
                    _sha512sums.append(_sha512.hexdigest())
                finally:
                    # 确保无论成功与否都删除已下载的文件，释放磁盘空间
                    if _f_loc.exists():
                        _f_loc.unlink()
                        logger.debug(f"Deleted cache file after checksum calculation: {_f_loc}")

            # 将校验和信息填入 manifest
            if len(_facts["distfiles"]) == len(_sizes) == len(_sha256sums) == len(_sha512sums):
                for _i in range(0, len(_sizes)):
                    _facts["distfiles"][_i]["size"] = _sizes[_i]
                    _facts["distfiles"][_i]["checksums"] = {"sha256": _sha256sums[_i], "sha512": _sha512sums[_i]}
                    _facts["distfiles"][_i]["restrict"] = ["mirror"]
                return True

            return False

        def manifests_reasoning(_ma: Dict):
            """
            执行推理规则链

            使用前向链推理系统，循环执行规则直到没有规则可以应用为止
            """
            _rules: List[Callable[[Dict], bool]] = [
                manifests_r1,
                manifests_r5,
                manifests_r9,
            ]
            _update = False
            _count = 0

            # 最多执行 100 轮推理（防止无限循环）
            while _count < 100:
                for r in _rules:
                    _update = _update or r(_ma)

                if not _update:
                    break

                _count += 1
                _update = False

            if _update and _count >= 100:
                logger.warning("rule reasoning run so many times")

        # 11: 定义 manifest 验证函数
        # 验证生成的 manifest 是否符合格式要求

        def manifests_validate(_ma: Dict) -> bool:
            """
            验证 manifest 结构和内容的完整性

            使用深度优先搜索 (DFS) 遍历验证：
            - _key_must: 必须存在的字段
            - _key_may: 可选的字段
            """
            # 定义必须包含的字段模板
            # 注意: 空字符串表示该字段必须存在但值不限，空列表/字典表示类型要求
            _key_must = {
                "format": "v1",
                "metadata": {
                    "desc": "",
                    "vendor": {"name": "", "eula": "", },
                    "upstream_version": "",
                },
                "distfiles": [{
                    "name": "",
                    "size": "",
                    "urls": ["", ],
                    "restrict": ["", ],
                    "checksums": {"sha256": "", "sha512": "", },
                }, ],
                "blob": {
                    "distfiles": ["", ],
                },
                "provisionable": {
                    "strategy": "",
                    "partition_map": {},
                },
            }
            # 定义可选字段
            _key_may = {
                "provisionable": {
                    "disk": "",
                    "root": "",
                    "boot": "",
                    "uboot": "",
                },
            }

            def dfs_validate(_templt: Dict, _type: str, _rkeys: Dict) -> bool:
                """
                使用 DFS 验证 manifest 结构

                """
                if _type not in ["must", "may"]:
                    return False

                # DFS 遍历用的栈
                _histories: List[int] = [0, ]
                _keys: List[List[str]] = [[], ]
                _trees: List[Dict] = [{}, ]
                _branch: List[str] = []  # 当前路径

                _ts: List[str] = []
                for _k in _templt.keys():
                    _ts.append(_k)
                _keys.append(_ts)
                _histories.append(0)
                _trees.append(_templt)
                _i = 1

                while _i > 0:
                    while _histories[_i] < len(_keys[_i]):
                        _k = _keys[_i][_histories[_i]]
                        _v = _trees[_i][_k]
                        _branch.append(_k)

                        if isinstance(_v, str | List):
                            # 在 manifest 中查找对应的值
                            _rv = None
                            for _b in _branch:
                                if _rv is None:
                                    _rv = _rkeys.get(_b)
                                else:
                                    _rv = _rv.get(_b)

                                if _rv is None:
                                    break

                            if _rv is None:
                                # 键不存在
                                if _type == "must":
                                    logger.debug(f"no such key in check dict: {_branch}")
                                    return False
                                elif _type == "may":
                                    pass  # 可选字段不存在可以接受
                            else:
                                # 键存在，检查类型和值
                                if type(_rv) != type(_v):
                                    logger.debug(f"type not same: {_rv} != {_v} of {_branch}")
                                    return False
                                if isinstance(_rv, List) and ( len(_rv) == 0 or type(_rv[0]) != type(_v[0]) ):
                                    logger.debug(f"type not same: {_rv} != {_v} of {_branch}")
                                    return False
                                if isinstance(_rv, str) and _v != "" and _rv != _v:
                                    logger.debug(f"type is str but value must same: {_rv} != {_v} of {_branch}")
                                    return False

                            # 检查完这个分支，回溯
                            _branch.pop()
                            _histories[_i] += 1

                        elif isinstance(_v, Dict):
                            # 进入子树继续遍历
                            _ts: List[str] = []
                            for _k in _v.keys():
                                _ts.append(_k)
                            _keys.append(_ts)
                            _trees.append(_v)
                            _histories.append(0)
                            _i += 1

                    # 完成这一层的遍历，回溯
                    _histories.pop()
                    _keys.pop()
                    _trees.pop()
                    _i -= 1
                    if _i > 0:
                        _branch.pop()
                    _histories[_i] += 1

                return True

            # 验证必须字段和可选字段
            if not dfs_validate(_key_must, "must", _ma):
                logger.error(f"key must check failed")
                return False
            if not dfs_validate(_key_may, "may", _ma):
                logger.error(f"key may check failed")
                return False

            return True

        # 12: 开始生成循环
        # 遍历所有要生成的版本

        for gv in gen_vers:
            #  12.1 创建 upstream 对象
            # 根据 riko.toml 中的配置创建相应的 upstream 对象
            riko_toml_nvdat = riko_toml.get_nvchecker_dat()
            riko_toml_source = riko_toml_nvdat["source"]

            if riko_toml_source == "github":
                riko_toml_upstream = GithubUpstream(riko_toml_nvdat["github"], gv)
            elif riko_toml_source == "regex":
                source = riko_toml.get_source()

                file_url = source["regex_file_url"]
                file_url = file_url.replace("{{nvchecker.url}}", riko_toml_nvdat["url"])
                file_url = file_url.replace("{{upstream_version}}", gv)

                riko_toml_upstream = RegexUpstream(riko_toml_nvdat["url"], riko_toml_nvdat["regex"], file_url, source["regex_file_regex"])
            else:
                raise NotImplementedError(f"upstream source {riko_toml_source} not supported")

            # 复制原始 riko.yaml 模板
            riko_yaml = copy.deepcopy(riko_yaml_orig)

            riko_yaml_source = {}
            riko_yaml_cbs = {}
            manifest_ids = {}  # 跟踪每个 combo 的 manifest_id，用于数据库记录

            # 12.2 处理 riko.yaml 中的 source 配置
            # 从 riko.yaml 的 "source" 部分初始化基础配置
            if "source" in riko_yaml.keys():
                riko_yaml_source = tree_update({"format": riko_yaml["format"]}, riko_yaml["source"])

            # 12.3 为每个 combo 生成 manifest
            for i in range(0, len(gen_cbs)):
                if gen_cbs[i] in riko_yaml.keys():
                    combo_name = gen_cbs[i]
                    # 将 combo 特定的配置合并到基础配置中
                    riko_yaml_ast = tree_update(riko_yaml_source, riko_yaml[gen_cbs[i]])

                    old_version = gen_cbs_ov[i].get_version()
                    new_manifests = {"metadata": {"upstream_version": gv}}

                    # 在数据库中创建 manifest 生成记录
                    manifest_id = None
                    try:
                        manifest = recorder.record_manifest_generation(
                            package_name=up_name,
                            combo_name=combo_name,
                            version=gv,
                            status="running"
                        )
                        manifest_id = manifest.id
                        manifest_ids[combo_name] = manifest_id
                    except Exception as e:
                        logger.warning(f"[DB] Failed to create manifest record: {e}")

                    # 12.4 执行 riko.yaml 模板生成 manifest
                    try:
                        manifest_stage1 = riko_yaml_run(riko_toml_upstream, old_version, new_manifests, riko_yaml_ast)
                    except Exception as e:
                        # 记录错误到数据库
                        if manifest_id:
                            try:
                                import json
                                error_details_dict = {
                                    "error_type": type(e).__name__,
                                    "error_message": str(e)
                                }
                                error_code = getattr(e, 'code', None)
                                if error_code:
                                    error_details_dict["error_code"] = error_code

                                recorder.db.update_manifest_record(
                                    manifest_id,
                                    status="failed",
                                    error_type=type(e).__name__,
                                    error_message=str(e),
                                    error_code=error_code,
                                    error_details=json.dumps(error_details_dict)
                                )
                                logger.error(f"[DB] Updated manifest {manifest_id} to failed: {type(e).__name__}: {e}")
                            except Exception as db_err:
                                logger.warning(f"[DB] Failed to update manifest record: {db_err}")

                        riko_yaml_cbs[combo_name] = None
                        continue

                    # 12.5 提取版本号并存储结果
                    new_version = str(old_version)
                    if "version" in manifest_stage1:
                        new_version = manifest_stage1["version"]
                        manifest_stage1.pop("version")
                    riko_yaml_cbs[combo_name] = (new_version, manifest_stage1)

            # 13: 检查并加载 riko.py 自定义钩子
            # riko.py 可以定义自定义的 rikoring 和 post_rikoring 函数
            # 这些函数可以在 manifest 生成过程中执行自定义逻辑

            riko_py_rikoring = None
            riko_py_post_rikoring = None
            if riko_py_p.exists():
                # 动态加载 riko.py 模块
                riko_py_spec = importlib.util.spec_from_file_location(f"{up_name}/riko.py", riko_py_p)
                riko_py_module = importlib.util.module_from_spec(riko_py_spec)
                riko_py_spec.loader.exec_module(riko_py_module)

                # 查找 rikoring 函数（在 manifest 生成前执行）
                try:
                    riko_py_rikoring = getattr(riko_py_module, "rikoring")
                except AttributeError as e:
                    logger.debug(e)

                # 查找 post_rikoring 函数（在 manifest 生成后执行）
                try:
                    riko_py_post_rikoring = getattr(riko_py_module, "post_rikoring")
                except AttributeError as e:
                    logger.debug(e)

            # 14: 构建旧版本包列表
            old_versions: List[RikoPkg] = []
            for i in range(0, len(gen_cbs_ov)):
                pkg = RikoPkg(riko_toml.get_category(), gen_cbs[i], riko_toml.get_name(), gen_cbs_ov[i].version,
                              gen_cbs_ov[i].upstream_version)
                pkg.set_manifest(gen_cbs_ov[i].manifest)
                pkg.add_policies([p for p in gen_cbs_ov[i].policies])
                old_versions.append(pkg)

            # 15: 构建新版本包列表
            new_versions: List[RikoPkg] = []
            for i in range(0, len(gen_cbs_ov)):
                combo = gen_cbs[i]
                if riko_yaml_cbs.get(combo) is None:
                    logger.warning(f"Skipping failed combo: {combo}")
                    continue

                pkg = RikoPkg(riko_toml.get_category(), combo, riko_toml.get_name(), semver.Version.parse(riko_yaml_cbs[combo][0]), gv, riko_toml_upstream)
                pkg.set_manifest(riko_yaml_cbs[combo][1])
                new_versions.append(pkg)

            # 16: 执行 rikoring 钩子
            # rikoring 允许在 manifest 生成前修改包对象
            if riko_py_rikoring is not None and len(new_versions) > 0:
                try:
                    riko_py_rikoring(old_versions, new_versions)
                except Exception as e:
                    logger.error(e)
                    traceback.print_exc()

            # 17: 执行推理规则
            # 自动填充 manifest 的缺失信息（策略、校验和等）
            for n, m in riko_yaml_cbs.items():
                if m is None:
                    continue
                manifests_reasoning(m[1])

            # 18: 验证生成的 manifest
            for v in new_versions:
                ma, rd = v.get_manifest()
                assert not rd

                if manifests_validate(ma):
                    v.set_manifest_ready()
                else:
                    logger.error(f"manifest validation failed for package {v.get_combo()} version {ma["metadata"]["upstream_version"]}")
                    logger.info(f"see failed manifests content: {ma}")

                    # 更新数据库记录为失败状态
                    combo_name = v.get_combo()
                    if combo_name in manifest_ids:
                        try:
                            recorder.db.update_manifest_record(
                                manifest_ids[combo_name],
                                status="failed",
                                error_type="ValidationError",
                                error_message="Manifest validation failed"
                            )
                        except Exception as e:
                            logger.warning(f"[DB] Failed to update manifest record: {e}")

            # 19: 执行 post_rikoring 钩子
            # post_rikoring 允许在 manifest 验证后执行额外的处理
            if riko_py_post_rikoring is not None and len(new_versions) > 0:
                try:
                    riko_py_post_rikoring(old_versions, new_versions)
                except Exception as e:
                    logger.error(e)
                    traceback.print_exc()

            # 20: 处理 keep_back 策略
            # keep_back 策略: 如果新旧版本的文件校验和相同，则保留旧版本
            for i in range(0, len(new_versions)):
                if old_versions[i].accept_policy("keep_back"):
                    ma, rd = new_versions[i].get_manifest()
                    oma, _ = old_versions[i].get_manifest()
                    if not rd:
                        continue
                    if len(oma["distfiles"]) != len(ma["distfiles"]):
                        continue

                    # 比较新旧版本的文件校验和
                    sums = {}
                    osums = {}
                    for d in ma["distfiles"]:
                        sums[d["name"]] = (d["checksums"]["sha256"], d["checksums"]["sha512"])
                    for d in oma["distfiles"]:
                        osums[d["name"]] = (d["checksums"]["sha256"], d["checksums"]["sha512"])

                    same = True
                    for n, s in sums.items():
                        if n not in osums.keys():
                            same = False
                            break
                        if osums[n][0] != s[0] or osums[n][1] != s[1]:
                            same = False
                            break

                    # 如果校验和相同，标记为不准备发布
                    if same:
                        new_versions[i].set_manifest_not_ready()
                        logger.info(f"`keep_back` for package {new_versions[i].get_combo()}, version "
                                    f"{ma["metadata"]["upstream_version"]} and version "
                                    f"{oma["metadata"]["upstream_version"]} have same checksums")

                        combo_name = new_versions[i].get_combo()
                        if combo_name in manifest_ids:
                            try:
                                recorder.db.update_manifest_record(
                                    manifest_ids[combo_name],
                                    status="skipped",
                                    skip_reason="keep_back"
                                )
                            except Exception as e:
                                logger.warning(f"[DB] Failed to update manifest record: {e}")

            # 21: 写入 manifest 文件
            new_gen = False
            for v in new_versions:
                ma, rd = v.get_manifest()
                if not rd:
                    continue

                # 创建目录并写入 toml 文件
                ensure_dir(riko_manifests_dir / v.get_category())
                ensure_dir(riko_manifests_dir / v.get_category() / v.get_combo())
                # 对于包含 -trunk 的版本（如 armbian-musepipro），使用完整的 upstream_version 作为文件名
                upstream_ver = ma.get("metadata", {}).get("upstream_version", "")
                if upstream_ver and "-trunk" in upstream_ver:
                    version_str = upstream_ver
                else:
                    version_str = str(v.get_version())
                new_toml = riko_manifests_dir / v.get_category() / v.get_combo() / f"{version_str}.toml"
                with open(new_toml, "wb") as nt:
                    tomli_w.dump(ma, nt)

                # 使用 ruyi 命令格式化 manifest
                cmd: List[str] = ["ruyi", "admin", "format-manifest", str(new_toml), ]
                env = os.environ.copy()

                process = subprocess.Popen(cmd, env=env)
                ret = process.wait()
                if ret != 0:
                    raise subprocess.CalledProcessError(ret, cmd)

                new_gen = True
                logger.info(f"new manifest for package {v.get_combo()} version {ma["metadata"]["upstream_version"]}")

                # 更新数据库记录为成功状态
                combo_name = v.get_combo()
                if combo_name in manifest_ids:
                    try:
                        manifest_size = new_toml.stat().st_size if new_toml.exists() else 0
                        manifest_hash = hashlib.sha256(new_toml.read_bytes()).hexdigest() if new_toml.exists() else ""

                        recorder.db.update_manifest_record(
                            manifest_ids[combo_name],
                            status="success",
                            manifest_path=str(new_toml),
                            manifest_size=manifest_size,
                            manifest_hash=manifest_hash
                        )
                    except Exception as e:
                        logger.warning(f"[DB] Failed to update manifest record: {e}")

            if not new_gen:
                logger.warning(f"no manifest for upstream {riko_toml.get_name()} version {gv}")
