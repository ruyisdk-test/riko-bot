# riko/cli/manifests.py - 清单生成引擎


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

from .utils import ensure_dir
from ..api import RikoPkg
from ..config.const import riko_cache_dir, riko_manifests_dir, ruyi_pkgs_dir
from ..packages_index.manifests import PackageVersion
from ..rikoriko import get_riko
from ..upstreams.github import GithubUpstream
from ..upstreams.regex import RegexUpstream
# 数据库记录工具
from ..database import record_command  # 数据库记录装饰器
from ..database import get_recorder  # 数据库记录器

logger = logging.getLogger(__name__)


@record_command("manifests")
def manifests(up_name: str, gen_vers: List[str], down_grade: bool):

    recorder = get_recorder()

    # nvchecker result
    result = get_riko().get_nvchecker_result(up_name)
    # {
    #     "name": "LicheeRV-Nano-Build",
    #     "event": "updated",
    #     "old_version": "0.20260107.0",
    #     "version": "0.20260114.0"
    # }
    if result is None:
        logger.error("No such nvchecker upstream %s", up_name)
        logger.error("May be new package")
    else:
        # if no gen_vers given, let nvchecker deside
        if len(gen_vers) == 0:
            gen_vers.append(result["version"])
    if result is None:
        # this empty old_ver is used as a flag
        # TODO: better resolution
        old_ver = ""
    elif result["event"] == "updated":
        old_ver = result["old_version"]
    else:
        old_ver = result["version"]
        if not down_grade:
            logger.warning("Already updated")
            return
    # check list
    if old_ver in gen_vers:
        logger.warning(f"Remove old version `{old_ver}` from generate version list")
        gen_vers.remove(old_ver)

    if len(gen_vers) == 0:
        logger.warning("No version to be generated")
        return

    logger.info(f"Generate {up_name} manifests for versions {gen_vers}")

    # load riko.toml config
    riko_toml = get_riko().get_ruyi_package(up_name)
    if riko_toml is None:
        raise FileNotFoundError(f"No riko upstream package `{up_name}` found")

    # load old packages-index manifest
    gen_cbs: List[str] = riko_toml.get_combos()
    gen_cbs_ov: List[PackageVersion] = []
    for c in gen_cbs:
        if old_ver:
            pkg_ver = get_riko().get_packages_index_manifest(riko_toml.get_category(), c, old_ver)
            if pkg_ver is None:
                if "keep_back" in riko_toml.get_policy(c):
                    pkg_ver = get_riko().get_packages_index_latest(riko_toml.get_category(), c)
                    pkg_ver.add_policies(riko_toml.get_policy(c))
                    logger.debug(f"no ruyi packages-index manifest for category `{riko_toml.get_category()}` "
                                 f"package {c} version {old_ver} found")
                    logger.debug(f"use `keep_back` policy, find ruyi packages-index manifest of category "
                                 f"`{riko_toml.get_category()}` package {c} version {pkg_ver.upstream_version}")
                    logger.info(f"{up_name} manifest {c} combo base on old version `{pkg_ver.upstream_version}`")
                else:
                    logger.info(f"No ruyi packages-index manifest for category `{riko_toml.get_category()}` "
                                f"package {c} version {old_ver} found")
            gen_cbs_ov.append(pkg_ver)
        else:
            # TODO: when empty old_ver, push fake old ver
            # TODO: * we should design a version base support
            # TODO: * design a list of manual maintained toml list
            # TODO: * design a list of ignored upstream version list
            gen_cbs_ov.append(PackageVersion(semver.Version.parse("0.0.0"), "0.0.0", {}))

    # output dir
    ensure_dir(riko_cache_dir)
    ensure_dir(riko_manifests_dir)

    riko_py_p = ruyi_pkgs_dir / riko_toml.get_category() / up_name / "riko.py"
    riko_yaml_p = ruyi_pkgs_dir / riko_toml.get_category() / up_name / "riko.yaml"

    if not riko_yaml_p.exists():
        logger.fatal("You must use riko.yaml in this riko version") # 修改拼写错误
        return

    riko_yaml_orig: Dict = yaml.safe_load(riko_yaml_p.read_text())
    assert riko_yaml_orig["format"] == "v1"

    # riko.yaml parsing functions
    def tree_parse_inner(key: str, value: Dict | List | str) -> Dict:
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
            # remain some str unchanged as str
            if re.match(r"^[a-zA-Z0-9 ,\-+.]+$", value):
                return {key: value}
            # treat rest str as expr
            return {key: ast.parse(value, mode="eval")}
        elif value is None:
            return {key: ""}
        else:
            raise RuntimeError(f"Unexpected type {type(value)}")

    def tree_update_inner(tree_old: Dict, tree_up: Dict) -> None:
        for k in tree_up.keys():
            if k in tree_old.keys() and isinstance(tree_old[k], Dict) and isinstance(tree_up[k], Dict):
                # keep old keys in old Dict
                tree_update_inner(tree_old[k], tree_up[k])
            else:
                tree_old[k] = tree_up[k]

    def tree_update(tree_old: Dict, tree_raw: Dict) -> Dict:
        tree_new = copy.deepcopy(tree_old)

        tree_update_inner(tree_new, tree_parse_inner("k", tree_raw)["k"])

        return tree_new

    # riko.yaml ast check function
    def riko_yaml_ast_check(exp: ast.Expression, g_vars: Dict, g_calls: Dict) -> bool:
        _ast_allowed = (ast.Expression, ast.Call, ast.Name, ast.Load, ast.Constant, ast.Tuple)
        # TODO:
        return True

    # riko.yaml running functions
    def riko_yaml_run(_up, _ov: semver.Version, nm: Dict, ym: Dict) -> Dict:
        # riko.yaml vals
        _upstream_version = nm["metadata"]["upstream_version"]
        _files = {}
        _label = []

        # riko.yaml utils
        def _file(_name_url: Tuple[str, str]) -> str:
            if _name_url[0] not in _files.keys():
                _files[_name_url[0]] = {}

            _files[_name_url[0]]["url"] = _name_url[1]
            return _name_url[0]

        def _uncompress(_orig: str) -> str:
            _tars = [".tar.gz", ".tar.bz2", ".tar.lz4", ".tar.xz", ".tar.zst", ".gz", ".bz2", ".lz4", ".xz", ".zst", ".zip"]
            for t in _tars:
                if _orig.endswith(t):
                    return _orig[:-len(t)]
            return _orig

        def _map_and_uncompress(_name: str, _map: str):
            if _name not in _files.keys():
                _files[_name] = {}

            _files[_name]["map"] = _map
            _files[_name]["uncompressed"] = _uncompress(_name)

        # riko.yaml api
        def _version(major=None, minor=None, patch=None) -> str:
            _nv = _ov
            if major is not None:
                _nv = _nv.replace(major=major)
            if minor is not None:
                _nv = _nv.replace(minor=minor)
            if patch is not None:
                _nv = _nv.replace(patch=patch)

            return str(_nv)

        def _assign(_parm) -> str:
            return str(_parm)

        def _substring(_sub: str) -> Tuple[str, str]:
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
            if _label[-1] == "name" and _label[-2] == "distfiles":
                if isinstance(_up, GithubUpstream):
                    return _up.get_release_assert_regex(_pat)
                elif isinstance(_up, RegexUpstream):
                    return _up.get_release_assert_regex(_pat)
                else:
                    raise NotImplementedError(f"upstream source {_up.source} not supported")
            else:
                raise NotImplementedError(f"substream not implemented for _label {_label}")

        def _titan(_name_url: Tuple[str, str]) -> str:
            _map_and_uncompress(_name_url[0], "titan")
            return _file(_name_url)

        def _live(_name_url: Tuple[str, str]) -> str:
            _map_and_uncompress(_name_url[0], "live")
            return _file(_name_url)

        def _disk(_name_url: Tuple[str, str]) -> str:
            _map_and_uncompress(_name_url[0], "disk")
            return _file(_name_url)

        def _root(_name_url: Tuple[str, str]) -> str:
            _map_and_uncompress(_name_url[0], "root")
            return _file(_name_url)

        def _boot(_name_url: Tuple[str, str]) -> str:
            _map_and_uncompress(_name_url[0], "boot")
            return _file(_name_url)

        def _uboot(_name_url: Tuple[str, str]) -> str:
            _map_and_uncompress(_name_url[0], "uboot")
            return _file(_name_url)

        # bfs run ast
        def _ast_run(_ym_t: Dict):
            for k, v in _ym_t.items():
                _label.append(k)

                if isinstance(v, ast.Expression):
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
                    if riko_yaml_ast_check(v, _g_vars, _g_calls):
                        _ym_t[k] = eval(compile(v, filename="<expr>", mode="eval"), _g_vars | _g_calls)
                        if not isinstance(_ym_t[k], str):
                            _ym_t[k] = f"value not str but {type(_ym_t[k])}"
                    else:
                        _ym_t[k] = "AST check failed"
                elif isinstance(v, str):
                    pass
                elif isinstance(v, Dict):
                    _ast_run(v)
                elif isinstance(v, List):
                    for d in v:
                        _ast_run(d)
                else:
                    raise RuntimeError(f"Unexpected type {type(v)}")

                _label.pop()

        _ast_run(ym)

        # info in _files
        if "provisionable" not in ym.keys():
            ym["provisionable"] = {"partition_map": {}}
        for ff in ym["distfiles"]:
            ff["urls"] = [_files[ff["name"]]["url"]]
            ym["provisionable"]["partition_map"][_files[ff["name"]]["map"]] = _files[ff["name"]]["uncompressed"]

        # info of _upstream_version
        ym["metadata"]["upstream_version"] = _upstream_version

        return ym

    # manifests reasoning rule set
    def manifests_r1(_facts: Dict) -> bool:
        if "provisionable" not in _facts.keys():
            return False

        _map = _facts.get("provisionable")
        if _map is None or "partition_map" not in _map.keys() or "strategy" in _map.keys():
            return False

        _map: Dict = _map["partition_map"]
        _strategy = ""
        if len(_map) == 1:
            if "disk" in _map.keys() or "live" in _map.keys():
                _strategy = "dd-v1"
            elif "uboot" in _map.keys():
                _strategy = "fastboot-v1(lpi4a-uboot)"
            elif "titan" in _map.keys():
                _strategy = "spacemit-k1-v1"
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
        if _strategy in ["dd-v1", "fastboot-v1(lpi4a-uboot)", "fastboot-v1", "spacemit-k1-v1"]:
            for _f in _facts["distfiles"]:
                _distfiles.append(_f["name"])

        if len(_distfiles) > 0:
            _facts["blob"]["distfiles"] = _distfiles
            return True

        return False

    def manifests_r9(_facts: Dict) -> bool:
        if "distfiles" not in _facts.keys():
            return False
        if not isinstance(_facts["distfiles"], List) or len(_facts["distfiles"]) == 0:
            return False

        _sizes = []
        _sha256sums = []
        _sha512sums = []

        for _d in _facts["distfiles"]:

            if "checksums" in _d.keys() or "size" in _d.keys():
                continue

            _url: str = _d["urls"][0]
            _f_loc = riko_cache_dir / _d["name"]
            # TODO: do not use curl
            _cmd: List[str] = ["curl", "-C", "-", "--retry", "3", "--retry-delay", "2", "--retry-all-errors",
                              "-L", _url, "-o", str(_f_loc), ]
            _env = os.environ.copy()

            if _f_loc.exists():
                _f_loc.unlink()

            _process = subprocess.Popen(_cmd, env=_env)
            _ret = _process.wait()
            if _ret != 0:
                raise subprocess.CalledProcessError(_ret, _cmd)

            # get size
            _sizes.append(os.path.getsize(_f_loc))

            # calculate hash
            _sha256 = hashlib.sha256()
            _sha512 = hashlib.sha512()

            with open(_f_loc, "rb") as _f:
                while True:
                    _c = _f.read(4 * 1024)
                    if not _c:
                        break

                    _sha256.update(_c)
                    _sha512.update(_c)

            _sha256sums.append(_sha256.hexdigest())
            _sha512sums.append(_sha512.hexdigest())

        if len(_facts["distfiles"]) == len(_sizes) == len(_sha256sums) == len(_sha512sums):
            for _i in range(0, len(_sizes)):
                _facts["distfiles"][_i]["size"] = _sizes[_i]
                _facts["distfiles"][_i]["checksums"] = {"sha256": _sha256sums[_i], "sha512": _sha512sums[_i]}
                _facts["distfiles"][_i]["restrict"] = ["mirror"]
            return True

        return False

    def manifests_reasoning(_ma: Dict):
        _rules: List[Callable[[Dict], bool]] = [
            manifests_r1,
            manifests_r5,
            manifests_r9,
        ]
        _update = False
        _count = 0

        while _count < 100:
            for r in _rules:
                _update = _update or r(_ma)

            if not _update:
                break

            _count += 1
            _update = False

        if _update and _count >= 100:
            logger.warning("rule reasoning run so many times")

    def manifests_validate(_ma: Dict) -> bool:

        # empty type to show its type, List cannot be empty, Dict can be empty
        # but List and Dict cannot be empty in real manifests
        # if str not empty, value in manifest must be equal to that in the template
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
        _key_may = {
            "provisionable": {
                "disk": "",
                "root": "",
                "boot": "",
                "uboot": "",
            },
        }

        def dfs_validate(_templt: Dict, _type: str, _rkeys: Dict) -> bool:
            if _type not in ["must", "may"]:
                return False

            _histories: List[int] = [0, ]
            _keys: List[List[str]] = [[], ]
            _trees: List[Dict] = [{}, ]
            _branch: List[str] = []

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
                        _rv = None
                        for _b in _branch:
                            if _rv is None:
                                _rv = _rkeys.get(_b)
                            else:
                                _rv = _rv.get(_b)

                            if _rv is None:
                                break

                        if _rv is None:
                            if _type == "must":
                                logger.debug(f"no such key in check dict: {_branch}")
                                return False
                            elif _type == "may":
                                pass
                        else:
                            if type(_rv) != type(_v):
                                logger.debug(f"type not same: {_rv} != {_v} of {_branch}")
                                return False
                            if isinstance(_rv, List) and ( len(_rv) == 0 or type(_rv[0]) != type(_v[0]) ):
                                logger.debug(f"type not same: {_rv} != {_v} of {_branch}")
                                return False
                            if isinstance(_rv, str) and _v != "" and _rv != _v:
                                logger.debug(f"type is str but value must same: {_rv} != {_v} of {_branch}")
                                return False

                        # check end on this branch
                        _branch.pop()
                        # next branch
                        _histories[_i] += 1

                    elif isinstance(_v, Dict):
                        # entre this tree
                        _ts: List[str] = []
                        for _k in _v.keys():
                            _ts.append(_k)
                        _keys.append(_ts)
                        _trees.append(_v)
                        _histories.append(0)
                        _i += 1

                # finish this depth
                _histories.pop()
                _keys.pop()
                _trees.pop()
                _i -= 1
                if _i > 0:
                    _branch.pop()
                _histories[_i] += 1

            return True

        if not dfs_validate(_key_must, "must", _ma):
            logger.error(f"key must check failed")
            return False
        if not dfs_validate(_key_may, "may", _ma):
            logger.error(f"key may check failed")
            return False

        return True

    # generating
    for gv in gen_vers:
        # get UpstreamLike from riko.toml
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

        riko_yaml = copy.deepcopy(riko_yaml_orig)

        riko_yaml_source = {}
        riko_yaml_cbs = {}
        manifest_ids = {}  # 跟踪每个 combo 的 manifest_id
        # initial packages-index toml cfgs from "source" section in riko.yaml
        if "source" in riko_yaml.keys():
            riko_yaml_source = tree_update({"format": riko_yaml["format"]}, riko_yaml["source"])
        # generate each combo
        for i in range(0, len(gen_cbs)):
            if gen_cbs[i] in riko_yaml.keys():
                combo_name = gen_cbs[i]
                # update toml cfgs from each package section in riko.yaml
                riko_yaml_ast = tree_update(riko_yaml_source, riko_yaml[gen_cbs[i]])

                old_version = gen_cbs_ov[i].get_version()
                new_manifests = {"metadata": {"upstream_version": gv}}

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

                try:
                    manifest_stage1 = riko_yaml_run(riko_toml_upstream, old_version, new_manifests, riko_yaml_ast)
                except Exception as e:
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

                new_version = str(old_version)
                if "version" in manifest_stage1:
                    new_version = manifest_stage1["version"]
                    manifest_stage1.pop("version")
                riko_yaml_cbs[combo_name] = (new_version, manifest_stage1)

        # check riko.py
        riko_py_rikoring = None
        riko_py_post_rikoring = None
        if riko_py_p.exists():

            # find functions
            riko_py_spec = importlib.util.spec_from_file_location(f"{up_name}/riko.py", riko_py_p)
            riko_py_module = importlib.util.module_from_spec(riko_py_spec)
            riko_py_spec.loader.exec_module(riko_py_module)

            try:
                riko_py_rikoring = getattr(riko_py_module, "rikoring")
            except AttributeError as e:
                logger.debug(e)

            try:
                riko_py_post_rikoring = getattr(riko_py_module, "post_rikoring")
            except AttributeError as e:
                logger.debug(e)

        # old version
        old_versions: List[RikoPkg] = []
        for i in range(0, len(gen_cbs_ov)):
            pkg = RikoPkg(riko_toml.get_category(), gen_cbs[i], riko_toml.get_name(), gen_cbs_ov[i].version,
                          gen_cbs_ov[i].upstream_version)
            pkg.set_manifest(gen_cbs_ov[i].manifest)
            pkg.add_policies([p for p in gen_cbs_ov[i].policies])
            old_versions.append(pkg)

        # new version
        new_versions: List[RikoPkg] = []
        for i in range(0, len(gen_cbs_ov)):
            combo = gen_cbs[i]
            if riko_yaml_cbs.get(combo) is None:
                logger.warning(f"Skipping failed combo: {combo}")
                continue

            pkg = RikoPkg(riko_toml.get_category(), combo, riko_toml.get_name(), semver.Version.parse(riko_yaml_cbs[combo][0]), gv, riko_toml_upstream)
            pkg.set_manifest(riko_yaml_cbs[combo][1])
            new_versions.append(pkg)

        # rikoring
        if riko_py_rikoring is not None and len(new_versions) > 0:
            try:
                riko_py_rikoring(old_versions, new_versions)
            except Exception as e:
                logger.error(e)
                traceback.print_exc()

        for n, m in riko_yaml_cbs.items():
            if m is None:
                continue
            manifests_reasoning(m[1])

        for v in new_versions:
            ma, rd = v.get_manifest()
            assert not rd

            if manifests_validate(ma):
                v.set_manifest_ready()
            else:
                logger.error(f"manifest validation failed for package {v.get_combo()} version {ma["metadata"]["upstream_version"]}")
                logger.info(f"see failed manifests content: {ma}")

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

        # post_rikoring
        if riko_py_post_rikoring is not None and len(new_versions) > 0:
            try:
                riko_py_post_rikoring(old_versions, new_versions)
            except Exception as e:
                logger.error(e)
                traceback.print_exc()

        for i in range(0, len(new_versions)):
            if old_versions[i].accept_policy("keep_back"):
                ma, rd = new_versions[i].get_manifest()
                oma, _ = old_versions[i].get_manifest()
                if not rd:
                    continue
                if len(oma["distfiles"]) != len(ma["distfiles"]):
                    continue

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

        new_gen = False
        for v in new_versions:
            ma, rd = v.get_manifest()
            if not rd:
                continue

            ensure_dir(riko_manifests_dir / v.get_category())
            ensure_dir(riko_manifests_dir / v.get_category() / v.get_combo())
            new_toml = riko_manifests_dir / v.get_category() / v.get_combo() / f"{str(v.get_version())}.toml"
            with open(new_toml, "wb") as nt:
                tomli_w.dump(ma, nt)

            cmd: List[str] = ["ruyi", "admin", "format-manifest", str(new_toml), ]
            env = os.environ.copy()

            process = subprocess.Popen(cmd, env=env)
            ret = process.wait()
            if ret != 0:
                raise subprocess.CalledProcessError(ret, cmd)

            new_gen = True
            logger.info(f"new manifest for package {v.get_combo()} version {ma["metadata"]["upstream_version"]}")

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
