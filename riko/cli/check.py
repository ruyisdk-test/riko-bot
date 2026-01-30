import json
import logging
import os
import subprocess

from typing import Dict, List

from .utils import ensure_dir
from ..config.const import basedir, nvchecker_datadir, riko_datadir, ruyi_datadir, ruyi_cache_dir, ruyi_state_dir, \
    ruyi_data_dir, ruyi_config_dir, ruyi_config, ruyi_config_extra, nvchecker_config, nvchecker_result, nvchecker_key
from ..rikoriko import get_riko
from ..database import record_command  # 添加装饰器导入
from ..database import get_recorder  # 添加记录器导入

logger = logging.getLogger(__name__)


def _ensure_riko_path() -> None:
    ensure_dir(riko_datadir)


def _ensure_nvchecker_path() -> None:
    ensure_dir(nvchecker_datadir)


def _ensure_ruyi_path() -> None:
    ensure_dir(ruyi_datadir)
    ensure_dir(ruyi_config_dir)
    ensure_dir(ruyi_config_dir / 'ruyi')
    ensure_dir(ruyi_data_dir)
    ensure_dir(ruyi_cache_dir)
    ensure_dir(ruyi_state_dir)


def _ensure_paths() -> None:
    _ensure_riko_path()
    _ensure_nvchecker_path()
    _ensure_ruyi_path()


def _ensure_nvchecker_env(env: Dict) -> None:
    env['PYTHONPATH'] = str(basedir)


def _ensure_ruyi_env(env: Dict) -> None:
    env['XDG_CONFIG_HOME'] = str(ruyi_config_dir)
    env['XDG_DATA_HOME'] = str(ruyi_data_dir)
    env['XDG_CACHE_HOME'] = str(ruyi_cache_dir)
    env['XDG_STATE_HOME'] = str(ruyi_state_dir)


@record_command("check")
def check() -> None:
    _ensure_paths()
    with open(ruyi_config_dir / "ruyi" / "config.toml", "w") as cfg:
        cfg.write(ruyi_config + "\n" + ruyi_config_extra)

    logger.info("run `ruyi update`")
    cmd: List[str] = ["ruyi", "update"]
    env = os.environ.copy()
    rfd, wfd = os.pipe()

    _ensure_ruyi_env(env)
    process = subprocess.Popen(cmd, stdout=wfd, stderr=wfd, env=env)
    os.close(wfd)

    out = os.fdopen(rfd)
    output = out.read()
    out.close()

    ret = process.wait()
    if ret != 0:
        raise subprocess.CalledProcessError(ret, cmd, output)

    if not (ruyi_cache_dir / "ruyi" / "packages-index").exists():
        raise FileNotFoundError(ruyi_cache_dir / "ruyi" / "packages-index")

    logger.info("prepare for `nvchecker`")
    get_riko().generate_nvchecker_config()
    get_riko().generate_nvchecker_old_ver()

    logger.info("run `nvchecker`")
    rfd, wfd = os.pipe()
    cmd: List[str] = ["nvchecker", "--logger", "both", "--json-log-fd", str(wfd), "-c", nvchecker_config]
    env = os.environ.copy()
    _ensure_nvchecker_env(env)

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
