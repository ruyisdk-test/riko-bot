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

    @staticmethod
    def _ensure_riko_path() -> None:
        ensure_dir(riko_datadir)

    @staticmethod
    def _ensure_nvchecker_path() -> None:
        ensure_dir(nvchecker_datadir)

    @staticmethod
    def _ensure_ruyi_path() -> None:
        ensure_dir(ruyi_datadir)
        ensure_dir(ruyi_config_dir)
        ensure_dir(ruyi_config_dir / 'ruyi')
        ensure_dir(ruyi_data_dir)
        ensure_dir(ruyi_cache_dir)
        ensure_dir(ruyi_state_dir)

    @staticmethod
    def _ensure_paths() -> None:
        CheckService._ensure_riko_path()
        CheckService._ensure_nvchecker_path()
        CheckService._ensure_ruyi_path()

    @staticmethod
    def _ensure_nvchecker_env(env: Dict) -> None:
        env['PYTHONPATH'] = str(basedir)

    @staticmethod
    def _ensure_ruyi_env(env: Dict) -> None:
        env['XDG_CONFIG_HOME'] = str(ruyi_config_dir)
        env['XDG_DATA_HOME'] = str(ruyi_data_dir)
        env['XDG_CACHE_HOME'] = str(ruyi_cache_dir)
        env['XDG_STATE_HOME'] = str(ruyi_state_dir)

    @staticmethod
    def _repair_ruyi_cache() -> bool:
        # Reset the local packages-index cache to the remote via git fetch + reset --hard
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
        # Ask ruyi for the real local_path and fall back to the const path on failure
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

        packages_index_dir = CheckService._resolve_ruyi_packages_index_dir()
        if packages_index_dir != ruyi_packages_index_dir:
            logger.warning(
                f"ruyi reports packages-index at {packages_index_dir}, "
                f"different from fixed path {ruyi_packages_index_dir}; using reported path"
            )
        if not packages_index_dir.exists():
            raise FileNotFoundError(packages_index_dir)
        logger.info(f"packages-index repo: {packages_index_dir}")

        # Sync the reported path so generate_nvchecker_old_ver() loads old versions from it
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
