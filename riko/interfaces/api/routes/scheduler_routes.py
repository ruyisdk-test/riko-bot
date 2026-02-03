"""
Scheduler routes for the Riko API

Provides endpoints for scheduler management operations.
"""

import logging
from fastapi import APIRouter, HTTPException, Body

from ..models.schemas import SchedulerStartRequest
from ....services.scheduler_service import (
    start_scheduler,
    stop_scheduler,
    scheduler_status,
    daily_check_and_pr
)
from ....database import set_trigger_source

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.post("/start")
def api_start_scheduler(
    request: SchedulerStartRequest = Body(default=None)
):
    """
    启动定时调度器

    HTTP 方法：POST（修改状态）
    请求体（可选）：{} （可选 hour/minute）
    返回：调度器状态
    注：当前默认为每天凌晨 2 点运行
    """
    # 如果没有提供请求体，使用默认值
    if request is None:
        request = SchedulerStartRequest()

    logger.info("[API] Starting scheduler")

    try:
        # 设置触发源为 API
        set_trigger_source("api")

        start_scheduler(request.hour, request.minute)
        return {
            "message": f"Scheduler started, will run daily at {request.hour:02d}:{request.minute:02d}",
            "status": scheduler_status()
        }
    except Exception as e:
        logger.error(f"[API] Failed to start scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
def api_stop_scheduler():
    """
    停止定时调度器

    HTTP 方法：POST（修改状态）
    返回：调度器状态
    """
    logger.info("[API] Stopping scheduler")

    try:
        stop_scheduler()
        return {
            "message": "Scheduler stopped",
            "status": scheduler_status()
        }
    except Exception as e:
        logger.error(f"[API] Failed to stop scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def api_scheduler_status():
    """
    获取调度器状态

    HTTP 方法：GET（查询操作）
    返回：调度器状态和任务列表
    """
    logger.info("[API] Getting scheduler status")

    try:
        return scheduler_status()
    except Exception as e:
        logger.error(f"[API] Failed to get scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger")
def api_trigger_daily_check():
    """
    手动触发每日检查和 PR 任务

    HTTP 方法：POST（触发操作）
    返回：执行结果
    """
    logger.info("[API] Triggering daily check")

    try:
        # 设置触发源为 API
        set_trigger_source("api")

        daily_check_and_pr()
        return {
            "message": "Daily check and PR task triggered",
            "status": scheduler_status()
        }
    except Exception as e:
        logger.error(f"[API] Failed to trigger daily check: {e}")
        raise HTTPException(status_code=500, detail=str(e))
