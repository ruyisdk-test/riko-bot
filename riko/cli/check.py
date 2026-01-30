"""
Check latest and setup riko local cache
"""

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

# ========== 目录创建工具函数 ==========

# 确保 riko 数据目录存在
def _ensure_riko_path() -> None:
    """
    创建 riko 的数据目录
    用于存储 riko 生成的配置和缓存文件
    """
    ensure_dir(riko_datadir)

# 确保 nvchecker 数据目录存在
def _ensure_nvchecker_path() -> None:
    """
    创建 nvchecker 的数据目录
    用于存储版本检查的配置文件
    """
    ensure_dir(nvchecker_datadir)

# 确保 ruyi 数据目录存在
def _ensure_ruyi_path() -> None:
    """
    创建 ruyi 工具所需的所有目录结构
    包括：配置目录、数据目录、缓存目录、状态目录
    """
    ensure_dir(ruyi_datadir)                    # ruyi 根目录
    ensure_dir(ruyi_config_dir)                 # 配置目录
    ensure_dir(ruyi_config_dir / 'ruyi')        # ruyi 子配置目录
    ensure_dir(ruyi_data_dir)                   # 数据目录
    ensure_dir(ruyi_cache_dir)                  # 缓存目录
    ensure_dir(ruyi_state_dir)                  # 状态目录

# 确保所有数据目录存在
def _ensure_paths() -> None:
    """
    确保所有工具的数据目录都已创建
    按顺序创建：riko、nvchecker、ruyi 的目录
    """
    _ensure_riko_path()      # 1. 创建 riko 目录
    _ensure_nvchecker_path() # 2. 创建 nvchecker 目录
    _ensure_ruyi_path()      # 3. 创建 ruyi 目录结构

# ========== 环境变量设置工具函数 ==========

# 确保 nvchecker 环境变量存在
def _ensure_nvchecker_env(env: Dict) -> None:
    """
    为 nvchecker 设置必要的环境变量
    PYTHONPATH: 指定 Python 模块搜索路径，包含当前项目根目录
    """
    env['PYTHONPATH'] = str(basedir)

# 确保 ruyi 环境变量存在
def _ensure_ruyi_env(env: Dict) -> None:
    """
    为 ruyi 工具设置 XDG 目录规范的环境变量
    XDG_CONFIG_HOME: 配置文件存储路径
    XDG_DATA_HOME: 数据文件存储路径
    XDG_CACHE_HOME: 缓存文件存储路径
    XDG_STATE_HOME: 状态文件存储路径
    """
    env['XDG_CONFIG_HOME'] = str(ruyi_config_dir)
    env['XDG_DATA_HOME'] = str(ruyi_data_dir)
    env['XDG_CACHE_HOME'] = str(ruyi_cache_dir)
    env['XDG_STATE_HOME'] = str(ruyi_state_dir)


@record_command("check")  # 使用装饰器自动记录数据库
def check() -> None:
    """
    主检查函数：执行完整的版本检查流程
    1. 创建必要目录
    2. 配置并运行 ruyi update
    3. 生成 nvchecker 配置
    4. 运行 nvchecker 检查版本更新
    """
    # ========== 步骤 1: 创建所有必要目录 ==========
    _ensure_paths()

    # ========== 步骤 2: 写入 ruyi 配置文件 ==========
    with open(ruyi_config_dir / "ruyi" / "config.toml", "w") as cfg:
        cfg.write(ruyi_config + "\n" + ruyi_config_extra)

    # ========== 步骤 3: 运行 ruyi update 命令 ==========
    logger.info("run `ruyi update`")
    cmd: List[str] = ["ruyi", "update"]
    env = os.environ.copy()      # 复制当前环境变量
    rfd, wfd = os.pipe()          # 创建管道用于捕获输出

    _ensure_ruyi_env(env)         # 将 ruyi 环境变量添加到子进程环境中
    process = subprocess.Popen(cmd, stdout=wfd, stderr=wfd, env=env)
    os.close(wfd)                 # 关闭写端

    out = os.fdopen(rfd)          # 从读端读取输出
    output = out.read()
    out.close()

    ret = process.wait()          # 等待进程结束
    if ret != 0:
        raise subprocess.CalledProcessError(ret, cmd, output)

    # 验证 ruyi update 是否成功创建了 packages-index 目录
    if not (ruyi_cache_dir / "ruyi" / "packages-index").exists():
        raise FileNotFoundError(ruyi_cache_dir / "ruyi" / "packages-index")

    # ========== 步骤 4: 生成 nvchecker 配置文件 ==========
    logger.info("prepare for `nvchecker`")
    get_riko().generate_nvchecker_config()   # 生成 nvchecker 配置文件
    get_riko().generate_nvchecker_old_ver()  # 生成旧版本文件

    # ========== 步骤 5: 运行 nvchecker 检查版本更新 ==========
    logger.info("run `nvchecker`")
    rfd, wfd = os.pipe()          # 创建管道用于接收 JSON 日志
    cmd: List[str] = ["nvchecker", "--logger", "both", "--json-log-fd", str(wfd), "-c", nvchecker_config]
    env = os.environ.copy()       # 复制当前环境变量
    _ensure_nvchecker_env(env)    # 设置 nvchecker 需要的环境变量

    # 如果存在密钥文件，添加到命令参数
    if nvchecker_key.exists():
        cmd.extend(['--keyfile', nvchecker_key])

    # 启动 nvchecker 进程，通过管道传递 JSON 日志
    process = subprocess.Popen(cmd, pass_fds=(wfd, ), env=env)
    os.close(wfd)                 # 关闭写端

    # ========== 步骤 6: 读取并格式化 nvchecker 输出 ==========
    out = os.fdopen(rfd)          # 从管道读取 JSON 日志
    with open(nvchecker_result, "w") as f:
        f.write("[")              # 开始 JSON 数组
        for l in out:
            f.write(f"{l.strip()},")  # 写入每一行 JSON 对象
        f.seek(f.tell() - 1, os.SEEK_SET)  # 回退删除最后一个逗号
        f.write("]")              # 结束 JSON 数组
    out.close()

    ret = process.wait()          # 等待 nvchecker 进程结束
    if ret != 0:
        raise subprocess.CalledProcessError(ret, cmd, output)

    # ========== 步骤 7: 格式化 JSON 结果文件 ==========
    with open(nvchecker_result, "r") as f:
        output = f.read()
    with open(nvchecker_result, "w") as f:
        json.dump(json.loads(output), f, indent=2)  # 美化 JSON 格式

    # 验证结果文件是否存在
    if not nvchecker_result.exists():
        raise FileNotFoundError(nvchecker_result)

    # ========== 步骤 8: 记录版本检查结果到数据库 ==========
    recorder = get_recorder()

    try:
        # 读取 nvchecker 结果
        with open(nvchecker_result, 'r') as f:
            nvchecker_results = json.load(f)

        # 记录每个包的版本检查结果
        total_count = 0
        updated_count = 0

        for result in nvchecker_results:
            package_name = result.get('name', 'unknown')
            new_version = result.get('version', '')
            old_version = result.get('old_version', '')
            event = result.get('event', 'no-result')
            url = result.get('url', '')

            # 确定检查状态
            check_status = 'updated' if event == 'updated' else 'unchanged'
            if event == 'error':
                check_status = 'error'

            # 记录到数据库
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

        # ========== 手动完成扫描记录，传入正确的统计信息 ==========
        recorder.finish_scan(
            status="completed",
            total_packages=total_count,
            updated_packages=updated_count,
            success_packages=total_count,  # 所有都算成功（即使没有更新）
            failed_packages=0
        )

    except Exception as e:
        logger.warning(f"[DB] Failed to record version checks: {e}")

        # ========== 记录失败时也要完成扫描 ==========
        try:
            recorder.finish_scan(
                status="failed",
                total_packages=0,
                updated_packages=0,
                success_packages=0,
                failed_packages=1
            )
        except Exception:
            pass  # 避免掩盖原始错误

        raise  # 重新抛出异常

    logger.info(f"Check completed successfully")
