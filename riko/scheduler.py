# riko/scheduler.py - 定时任务调度器
"""
APScheduler 定时任务管理器

"""

import logging
import signal
import sys
import time
from typing import List, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .cli.check import check
from .cli.manifests import manifests
from .cli.pr import pr
from .rikoriko import get_riko
from riko.database import get_recorder

logger = logging.getLogger(__name__)

# ========== 调度器实例 ==========
_scheduler: BackgroundScheduler = None

# 获取调度器实例（单例模式）
def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


# ========== 调度器管理 ==========
# 启动调度器
def start_scheduler(hour: int = 2, minute: int = 0):
    """
    启动调度器

    :param hour: 每天执行的小时（0-23，默认凌晨 2 点）
    :param minute: 每天执行的分钟（0-59，默认 0 分）
    """
    scheduler = get_scheduler()

    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")

        # 添加每日任务
        cron_expr = f"{minute} {hour} * * *"
        scheduler.add_job(
            daily_check_and_pr,
            trigger=CronTrigger.from_crontab(cron_expr),
            id="daily_check_and_pr",
            name="Daily version check and PR creation",
            replace_existing=True
        )
        logger.info(f"Daily job scheduled: {cron_expr} (daily at {hour:02d}:{minute:02d})")

# 停止调度器
def stop_scheduler():
    scheduler = get_scheduler()

    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")

# 获取调度器状态
def scheduler_status() -> Dict[str, Any]:
    scheduler = get_scheduler()

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
        })

    return {
        "running": scheduler.running,
        "jobs": jobs
    }

# 每日检查和 PR 创建任务
#
# 工作流程：
# 1. 开始顶层扫描
# 2. 执行 `riko check`（内部会自动记录版本更新）
# 3. 获取有更新的包
# 4. 对每个包：
#    a. 生成 manifests（内部会自动记录）
#    b. 创建 PR（TODO: 需要集成数据库记录）
#    c. 记录失败（如果失败）
# 5. 完成顶层扫描
# ========== 核心任务：每日检查和 PR 创建 ==========
def daily_check_and_pr() -> None:
    # 导入数据库记录器（支持嵌套调用）

    # 初始化记录器
    recorder = get_recorder()

    # 开始顶层扫描
    scan = recorder.start_scan(command="daily_check_and_pr", trigger_source="scheduler")

    logger.info("=" * 70)
    logger.info(f"Starting daily check and PR task (Scan ID: {scan.id})")
    logger.info("=" * 70)

    try:
        # ========== 步骤 1: 执行版本检查（内部会自动记录） ==========
        logger.info("[Step 1/3] Running version check...")
        check()
        logger.info("[Step 1/3] ✓ Version check completed")

        # ========== 步骤 2: 获取有更新的包 ==========
        logger.info("[Step 2/3] Getting updated packages...")
        riko = get_riko()
        updated_results = riko.get_nvchecker_results("updated")

        # 如果没有更新的包，直接结束
        if not updated_results:
            logger.info("No packages need updating")
            recorder.finish_scan(
                status="completed",
                total_packages=0,
                updated_packages=0,
                success_packages=0,
                failed_packages=0
            )
            return

        logger.info(f"Found {len(updated_results)} packages with updates:")
        # 记录每个更新的包的详细信息
        for result in updated_results:
            logger.info(f"  - {result['name']}: {result.get('old_version')} → {result['version']}")

        # ========== 步骤 3: 为每个包生成 manifests 并创建 PR ==========
        logger.info("[Step 3/3] Processing updated packages...")
        success_count = 0
        failed_packages = []

        for result in updated_results:
            package_name = result['name']
            new_version = result['version']

            logger.info(f"  [{success_count + 1}/{len(updated_results)}] {package_name}")

            try:
                # 3.1 生成 manifests（内部会自动记录）
                logger.info(f"    → Generating manifests...")
                manifests(package_name, [new_version], down_grade=False)
                logger.info(f"    ✓ Manifests generated")

                # 3.2 创建 PR（内部会自动记录，支持嵌套调用）
                logger.info(f"    → Creating PR...")
                from argparse import Namespace
                args = Namespace(
                    package_name=package_name,
                    branch_prefix=None,
                    github_token=None,
                    repo_owner=None,
                    repo_name=None,
                    base_branch=None
                )
                pr(args)
                logger.info(f"    ✓ PR created")

                success_count += 1

            except Exception as e:
                logger.error(f"    ✗ Failed: {e}")
                logger.error(f"      Error type: {type(e).__name__}")
                # pr() 和 manifests() 的装饰器会自动记录错误到数据库
                # 统计失败数量
                failed_packages.append(package_name)

        # ========== 完成顶层扫描 ==========
        recorder.finish_scan(
            status="completed" if not failed_packages else "partial_success",
            total_packages=len(updated_results),
            updated_packages=len(updated_results),
            success_packages=success_count,
            failed_packages=len(failed_packages)
        )

        logger.info("=" * 70)
        logger.info(f"Task completed: {success_count} success, {len(failed_packages)} failed")
        if failed_packages:
            logger.warning(f"Failed packages: {', '.join(failed_packages)}")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Task failed: {e}")
        logger.error(f"Error type: {type(e).__name__}")

        # 记录整体失败
        recorder.record_error(
            package_name="scheduler",
            error=e,
            failure_step="daily_check_and_pr",
            include_traceback=True
        )

        # 完成扫描（失败状态）
        recorder.finish_scan(
            status="failed",
            total_packages=0,
            updated_packages=0,
            success_packages=0,
            failed_packages=1
        )
        raise

# ========== CLI 命令 ==========

# 立即触发任务（CLI 命令）
def cmd_scheduler_trigger():
    print("Triggering daily check and PR task...")
    daily_check_and_pr()
    print("Task completed.")


# ========== 调度器辅助函数 ==========

def run_scheduler_daemon(hour: int = 2, minute: int = 0) -> None:
    """
    启动调度器并保持运行（守护进程模式）

    :param hour: 每天执行的小时（0-23，默认凌晨 2 点）
    :param minute: 每天执行的分钟（0-59，默认 0 分）
    """
    def handle_shutdown(signum, frame):
        """处理关闭信号（内部函数）"""
        logger.info(f"Received signal {signum}, shutting down...")
        stop_scheduler()
        sys.exit(0)

    # 注册信号处理（优雅退出）
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info(f"Starting scheduler daemon (runs daily at {hour:02d}:{minute:02d})...")
    logger.info("Press Ctrl+C to stop")

    # 启动调度器
    start_scheduler(hour, minute)

    try:
        # 保持主程序运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        # 清理资源
        logger.info("Shutting down scheduler...")
        stop_scheduler()
