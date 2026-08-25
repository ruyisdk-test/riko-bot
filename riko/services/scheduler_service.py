import asyncio
import logging
import signal
import sys
import time
from typing import List, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..interfaces.cli.check import check
from ..interfaces.cli.manifests import manifests
from ..interfaces.cli.pr import pr
from ..core import get_riko
from ..database import get_recorder, set_trigger_source
from ..services.check_service import CheckService
from ..services.manifest_service import ManifestService
from ..services.pr_service import PRService

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler = None

def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


def start_scheduler(hour: int = 2, minute: int = 0):
    scheduler = get_scheduler()

    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")

        cron_expr = f"{minute} {hour} * * *"
        scheduler.add_job(
            daily_check_and_pr,
            trigger=CronTrigger.from_crontab(cron_expr),
            id="daily_check_and_pr",
            name="Daily version check and PR creation",
            replace_existing=True
        )
        logger.info(f"Daily job scheduled: {cron_expr} (daily at {hour:02d}:{minute:02d})")

def stop_scheduler():
    scheduler = get_scheduler()

    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")

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

def daily_check_and_pr() -> None:
    set_trigger_source("scheduler")

    recorder = get_recorder()

    scan = recorder.start_scan(command="daily_check_and_pr", trigger_source="scheduler")

    logger.info("=" * 70)
    logger.info(f"Starting daily check and PR task (Scan ID: {scan.id})")
    logger.info("=" * 70)

    try:
        logger.info("[Step 1/3] Running version check...")
        CheckService.run()
        logger.info("[Step 1/3] ✓ Version check completed")

        logger.info("[Step 2/3] Getting updated packages...")
        riko = get_riko()
        updated_results = riko.get_nvchecker_results("updated")

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
        for result in updated_results:
            logger.info(f"  - {result['name']}: {result.get('old_version')} → {result['version']}")

        logger.info("[Step 3/3] Processing updated packages...")
        success_count = 0
        failed_packages = []

        for result in updated_results:
            package_name = result['name']
            new_version = result['version']

            logger.info(f"  [{success_count + 1}/{len(updated_results)}] {package_name}")

            try:
                logger.info(f"    → Generating manifests...")
                ManifestService.generate(package_name, [new_version], down_grade=False)
                logger.info(f"    ✓ Manifests generated")

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
                PRService.create(args)
                logger.info(f"    ✓ PR created")

                success_count += 1

            except Exception as e:
                logger.error(f"    ✗ Failed: {e}")
                logger.error(f"      Error type: {type(e).__name__}")
                failed_packages.append(package_name)

        final_status = "completed"
        if failed_packages:
            final_status = "partial_success" if success_count > 0 else "failed"

        recorder.finish_scan(
            status=final_status,
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

        try:
            from .telegramBot_service import notify_scan_summary

            updated_list = []
            for result in updated_results:
                updated_list.append({
                    "name": result['name'],
                    "old_version": result.get('old_version', '?'),
                    "new_version": result.get('version', '?')
                })

            failed_list = []
            for pkg in failed_packages:
                failed_list.append({"name": pkg})

            asyncio.run(notify_scan_summary(
                total_packages=len(updated_results),
                updated_packages=len(updated_results),
                success_packages=success_count,
                failed_packages=len(failed_packages),
                updated_list=updated_list,
                failed_list=failed_list
            ))
        except Exception as e:
            logger.error(f"[Telegram] Failed to send notification: {e}")

    except Exception as e:
        logger.error(f"Task failed: {e}")
        logger.error(f"Error type: {type(e).__name__}")

        recorder.record_error(
            package_name="scheduler",
            error=e,
            failure_step="daily_check_and_pr",
            include_traceback=True
        )

        recorder.finish_scan(
            status="failed",
            total_packages=0,
            updated_packages=0,
            success_packages=0,
            failed_packages=0
        )
        raise

def cmd_scheduler_trigger():
    print("Triggering daily check and PR task...")
    daily_check_and_pr()
    print("Task completed.")


def run_scheduler_daemon(hour: int = 2, minute: int = 0) -> None:
    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        stop_scheduler()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info(f"Starting scheduler daemon (runs daily at {hour:02d}:{minute:02d})...")
    logger.info("Press Ctrl+C to stop")

    start_scheduler(hour, minute)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        logger.info("Shutting down scheduler...")
        stop_scheduler()
