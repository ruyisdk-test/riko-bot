"""
Check Service - 版本检查服务

本模块提供版本检查的核心业务逻辑，从 CLI 层分离出来。
包含环境设置、ruyi update、nvchecker 执行等核心功能。
"""

import json
import logging
import os
import subprocess

from pathlib import Path
from typing import Dict, List

from ..config.const import basedir, nvchecker_datadir, riko_datadir, ruyi_datadir, ruyi_cache_dir, ruyi_state_dir, \
    ruyi_data_dir, ruyi_config_dir, ruyi_config, ruyi_config_extra, nvchecker_config, nvchecker_result, nvchecker_key, \
    ruyi_packages_index_dir
from ..core import get_riko
from ..database import record_command, get_recorder
from ..interfaces.cli.utils import ensure_dir

logger = logging.getLogger(__name__)


class CheckService:
    """版本检查服务类"""

    @staticmethod
    def _ensure_riko_path() -> None:
        """确保 riko 路径存在"""
        ensure_dir(riko_datadir)

    @staticmethod
    def _ensure_nvchecker_path() -> None:
        """确保 nvchecker 路径存在"""
        ensure_dir(nvchecker_datadir)

    @staticmethod
    def _ensure_ruyi_path() -> None:
        """确保 ruyi 路径存在"""
        ensure_dir(ruyi_datadir)
        ensure_dir(ruyi_config_dir)
        ensure_dir(ruyi_config_dir / 'ruyi')
        ensure_dir(ruyi_data_dir)
        ensure_dir(ruyi_cache_dir)
        ensure_dir(ruyi_state_dir)

    @staticmethod
    def _ensure_paths() -> None:
        """确保所有路径存在"""
        CheckService._ensure_riko_path()
        CheckService._ensure_nvchecker_path()
        CheckService._ensure_ruyi_path()

    @staticmethod
    def _ensure_nvchecker_env(env: Dict) -> None:
        """确保 nvchecker 环境变量存在"""
        env['PYTHONPATH'] = str(basedir)

    @staticmethod
    def _ensure_ruyi_env(env: Dict) -> None:
        """确保 ruyi 环境变量存在"""
        env['XDG_CONFIG_HOME'] = str(ruyi_config_dir)
        env['XDG_DATA_HOME'] = str(ruyi_data_dir)
        env['XDG_CACHE_HOME'] = str(ruyi_cache_dir)
        env['XDG_STATE_HOME'] = str(ruyi_state_dir)

    @staticmethod
    def _repair_ruyi_cache() -> bool:
        """
        修复 ruyi packages-index 缓存目录的 git 状态

        当 ``ruyi update`` 因 git 快进失败而报错时，通过 ``git fetch`` +
        ``git reset --hard`` 将本地缓存重置到远端状态。

        :return: 修复是否成功
        """
        cache_path = CheckService._resolve_ruyi_packages_index_dir()
        if not (cache_path / ".git").exists():
            return False
        try:
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=str(cache_path),
                capture_output=True,
                check=True,
                timeout=60,
            )
            subprocess.run(
                ["git", "reset", "--hard", "FETCH_HEAD"],
                cwd=str(cache_path),
                capture_output=True,
                check=True,
                timeout=30,
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=str(cache_path),
                capture_output=True,
                check=True,
                timeout=30,
            )
            logger.info("Repaired ruyi cache: git fetch + reset --hard successful")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to repair ruyi cache via git reset: {e}")
            return False

    @staticmethod
    def _ruyi_update() -> bytes:
        """运行 ``ruyi update``，返回 stdout/stderr 内容"""
        cmd: List[str] = ["ruyi", "update"]
        env = os.environ.copy()
        CheckService._ensure_ruyi_env(env)

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        output, _ = process.communicate()

        ret = process.returncode
        if ret != 0:
            raise subprocess.CalledProcessError(ret, cmd, output)
        return output

    @staticmethod
    def _resolve_ruyi_packages_index_dir() -> Path:
        """
        解析 ruyi 实际使用的 packages-index 仓库路径

        通过 ``ruyi --porcelain repo list`` 查询 ruyi 报告的 local_path，
        与 const 中固定的路径（沙箱配置里 [repo] local 指定的稳定路径）
        核对。若 ruyi 报告了不同的实际路径（例如 ruyi 升级后忽略
        repo.local 或改变内部布局），以 ruyi 报告为准；解析失败时
        回退到 const 固定路径。

        :return: ruyi 实际使用的仓库路径
        """
        try:
            env = os.environ.copy()
            CheckService._ensure_ruyi_env(env)
            process = subprocess.run(
                ["ruyi", "--porcelain", "repo", "list"],
                capture_output=True,
                env=env,
                timeout=30,
                check=True,
            )
            for line in process.stdout.decode("utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("id") == "ruyisdk":
                    local_path = entry.get("local_path")
                    if local_path:
                        return Path(local_path)
                    break
        except Exception as e:
            logger.warning(f"Failed to resolve ruyi packages-index path via `ruyi repo list`: {e}")

        return ruyi_packages_index_dir

    @staticmethod
    @record_command("check")
    def run() -> None:
        """
        执行版本检查

        功能：
        1. 确保所有路径存在
        2. 写入 ruyi 配置文件
        3. 执行 ruyi update
        4. 生成 nvchecker 配置
        5. 执行 nvchecker
        6. 记录结果到数据库
        """
        CheckService._ensure_paths()
        with open(ruyi_config_dir / "ruyi" / "config.toml", "w") as cfg:
            cfg.write(ruyi_config + "\n" + ruyi_config_extra)

        logger.info("run `ruyi update`")
        try:
            CheckService._ruyi_update()
        except subprocess.CalledProcessError as e:
            logger.warning(f"ruyi update failed (exit {e.returncode}), attempting to repair git cache")
            if CheckService._repair_ruyi_cache():
                logger.info("retrying `ruyi update` after cache repair")
                CheckService._ruyi_update()
            else:
                raise

        # 解析 ruyi 实际报告的仓库路径，与 const 固定路径核对
        packages_index_dir = CheckService._resolve_ruyi_packages_index_dir()
        if packages_index_dir != ruyi_packages_index_dir:
            logger.warning(
                f"ruyi reports packages-index at {packages_index_dir}, "
                f"different from fixed path {ruyi_packages_index_dir}; using reported path"
            )
        if not packages_index_dir.exists():
            raise FileNotFoundError(packages_index_dir)
        logger.info(f"packages-index repo: {packages_index_dir}")

        # 将 ruyi 实际报告的仓库路径同步给 Riko，避免后续
        # generate_nvchecker_old_ver() 仍从 const 固定路径加载旧版本。
        get_riko().set_packages_index_dir(packages_index_dir)

        logger.info("prepare for `nvchecker`")
        get_riko().generate_nvchecker_config()
        get_riko().generate_nvchecker_old_ver()

        logger.info("run `nvchecker`")
        rfd, wfd = os.pipe()
        cmd: List[str] = ["nvchecker", "--logger", "both", "--json-log-fd", str(wfd), "-c", nvchecker_config]
        env = os.environ.copy()
        CheckService._ensure_nvchecker_env(env)

        if nvchecker_key.exists():
            cmd.extend(['--keyfile', nvchecker_key])

        process = subprocess.Popen(cmd, pass_fds=(wfd, ), env=env)
        os.close(wfd)

        out = os.fdopen(rfd)
        with open(nvchecker_result, "w") as f:
            f.write("[")
            for l in out:
                f.write(f"{l.strip()},")
            f.seek(f.tell() - 1, os.SEEK_SET)
            f.write("]")
        out.close()

        ret = process.wait()
        if ret != 0:
            raise subprocess.CalledProcessError(ret, cmd, output)

        with open(nvchecker_result, "r") as f:
            output = f.read()
        with open(nvchecker_result, "w") as f:
            json.dump(json.loads(output), f, indent=2)

        if not nvchecker_result.exists():
            raise FileNotFoundError(nvchecker_result)
        recorder = get_recorder()

        try:
            with open(nvchecker_result, 'r') as f:
                nvchecker_results = json.load(f)

            total_count = 0
            updated_count = 0

            for result in nvchecker_results:
                package_name = result.get('name', 'unknown')
                new_version = result.get('version', '')
                old_version = result.get('old_version', '')
                event = result.get('event', 'no-result')
                url = result.get('url', '')

                check_status = 'updated' if event == 'updated' else 'unchanged'
                if event == 'error':
                    check_status = 'error'

                recorder.record_version_check(
                    package_name=package_name,
                    new_version=new_version,
                    old_version=old_version if old_version else None,
                    check_status=check_status,
                    nvchecker_event=event,
                    nvchecker_url=url
                )

                total_count += 1
                if event == 'updated':
                    updated_count += 1

            logger.info(f"[DB] Recorded {total_count} package checks ({updated_count} updated)")

            recorder.finish_scan(
                status="completed",
                total_packages=total_count,
                updated_packages=updated_count,
                success_packages=total_count,
                failed_packages=0
            )

        except Exception as e:
            logger.warning(f"[DB] Failed to record version checks: {e}")

            try:
                recorder.finish_scan(
                    status="failed",
                    total_packages=0,
                    updated_packages=0,
                    success_packages=0,
                    failed_packages=1
                )
            except Exception:
                pass

            raise

        logger.info(f"Check completed successfully")
