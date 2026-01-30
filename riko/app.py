#!/usr/bin/env python3
# riko/app.py - FastAPI Web 服务
"""
提供 HTTP API 接口来调用 riko 的各个功能

直接调用项目内部方法，不使用 subprocess
"""

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Optional, List
import logging

from .scheduler import (
    start_scheduler,
    stop_scheduler,
    scheduler_status,
    daily_check_and_pr
)
from .cli.check import check as check_command
from .cli.manifests import manifests as manifests_command
from .cli.pr import pr as pr_command
from .rikoriko import get_riko

logger = logging.getLogger(__name__)

# ========== 初始化 FastAPI 应用 ==========
app = FastAPI(
    title="Ruyi Packaging API",
    version="0.2.0",
    description="Riko 包管理和自动化工具 API"
)


# ========== 请求/响应模型 ==========

class CheckResponse(BaseModel):
    """版本检查响应"""
    total: int
    updated: int
    up_to_date: int
    errors: int
    packages: List[dict]


class ManifestsRequest(BaseModel):
    """Manifest 生成请求"""
    versions: Optional[List[str]] = None  # 要生成的版本列表
    down_grade: bool = False  # 是否降级生成


class ManifestsResponse(BaseModel):
    """Manifest 生成响应"""
    package_name: str
    combo_name: str
    version: str
    status: str  # success / failed / skipped
    manifest_path: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class PRRequest(BaseModel):
    """PR 创建请求"""
    branch_prefix: Optional[str] = None
    github_token: Optional[str] = None
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    base_branch: Optional[str] = None


class SchedulerStartRequest(BaseModel):
    """调度器启动请求（暂未使用，默认为每天凌晨2点）"""
    # 注：当前 scheduler.py 硬编码为每天凌晨2点，此参数暂未生效
    hour: int = 2
    minute: int = 0


# 版本检查
@app.get("/check", response_model=CheckResponse)
def api_check_versions():
    """
    触发版本检查

    HTTP 方法：GET（幂等操作）
    返回：检查结果统计
    """
    logger.info("[API] Received check request")

    try:
        # 直接调用 check 命令的核心逻辑
        riko = get_riko()
        riko.load_from_cache()  # 加载缓存数据
        nvchecker_results = riko.get_nvchecker_results("any")

        total = len(nvchecker_results)
        updated = 0
        up_to_date = 0
        errors = 0
        packages = []

        for result in nvchecker_results:
            pkg_name = result.get("name", "unknown")
            event = result.get("event")

            if event is None:
                errors += 1
                packages.append({
                    "name": pkg_name,
                    "status": "error",
                    "message": "No result"
                })
            elif event == "updated":
                updated += 1
                packages.append({
                    "name": pkg_name,
                    "status": "updated",
                    "old_version": result.get("old_version"),
                    "new_version": result.get("version")
                })
            elif event == "up-to-date":
                up_to_date += 1
                packages.append({
                    "name": pkg_name,
                    "status": "up-to-date",
                    "version": result.get("version")
                })

        logger.info(f"[API] Check completed: {total} total, {updated} updated, {up_to_date} up-to-date, {errors} errors")

        return CheckResponse(
            total=total,
            updated=updated,
            up_to_date=up_to_date,
            errors=errors,
            packages=packages
        )

    except Exception as e:
        logger.error(f"[API] Check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/check/run", response_model=CheckResponse)
def api_run_check():
    """
    执行版本检查（会记录到数据库）

    HTTP 方法：POST（执行操作）
    返回：检查结果统计
    """
    logger.info("[API] Received check run request")

    try:
        # 设置触发源为 API
        from .database import set_trigger_source
        set_trigger_source("api")

        # 执行 check 命令
        check_command()

        # 返回结果
        riko = get_riko()
        riko.load_from_cache()
        nvchecker_results = riko.get_nvchecker_results("any")

        total = len(nvchecker_results)
        updated = 0
        up_to_date = 0
        errors = 0
        packages = []

        for result in nvchecker_results:
            pkg_name = result.get("name", "unknown")
            event = result.get("event")

            if event is None:
                errors += 1
                packages.append({
                    "name": pkg_name,
                    "status": "error",
                    "message": "No result"
                })
            elif event == "updated":
                updated += 1
                packages.append({
                    "name": pkg_name,
                    "status": "updated",
                    "old_version": result.get("old_version"),
                    "new_version": result.get("version")
                })
            elif event == "up-to-date":
                up_to_date += 1
                packages.append({
                    "name": pkg_name,
                    "status": "up-to-date",
                    "version": result.get("version")
                })

        logger.info(f"[API] Check completed: {total} total, {updated} updated, {up_to_date} up-to-date, {errors} errors")

        return CheckResponse(
            total=total,
            updated=updated,
            up_to_date=up_to_date,
            errors=errors,
            packages=packages
        )

    except Exception as e:
        logger.error(f"[API] Check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 生成 Manifest
@app.post("/manifests/{package_name}")
def api_generate_manifests(
    package_name: str,
    request: ManifestsRequest = Body(default=None)
):
    """
    生成指定包的 Manifest
    请求体（可选）：
        {
            "versions": ["26.04"],  // 可选，要生成的版本列表
            "down_grade": false     // 可选，是否降级生成
        }
    返回：生成结果列表
    """
    # 如果没有提供请求体，使用默认值
    if request is None:
        request = ManifestsRequest()

    logger.info(f"[API] Received manifests request for {package_name}: {request}")

    try:
        # 设置触发源为 API
        from .database import set_trigger_source
        set_trigger_source("api")

        # 加载 riko 数据（确保能找到包配置）
        riko = get_riko()
        riko.load_from_cache()

        # 准备参数
        gen_vers = request.versions if request.versions else []
        down_grade = request.down_grade

        # 直接调用 manifests 命令
        manifests_command(package_name, gen_vers, down_grade)

        # 从数据库获取生成结果
        from .database import get_database
        from .database.models import ManifestRecord

        db = get_database()
        results = []

        with db.get_session() as session:
            from sqlalchemy import desc
            # 获取最近的 manifest 记录
            manifest_records = session.query(ManifestRecord).filter(
                ManifestRecord.package_name == package_name
            ).order_by(desc(ManifestRecord.created_at)).limit(50).all()

            # 在 session 内部转换为 Pydantic 模型（避免会话关闭后访问属性）
            for record in manifest_records:
                results.append(ManifestsResponse(
                    package_name=record.package_name,
                    combo_name=record.combo_name,
                    version=record.version,
                    status=record.status,
                    manifest_path=record.manifest_path,
                    error_type=record.error_type,
                    error_message=record.error_message
                ))

        logger.info(f"[API] Manifests generated for {package_name}: {len(results)} results")

        return results

    except FileNotFoundError as e:
        logger.error(f"[API] Package not found: {package_name}")
        raise HTTPException(status_code=404, detail=f"Package '{package_name}' not found")
    except Exception as e:
        logger.error(f"[API] Manifests generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 创建 PR
@app.post("/pr/{package_name}")
def api_create_pr(
    package_name: str,
    request: PRRequest = Body(default=None)
):
    """
    为指定包创建 PR

    HTTP 方法：POST（创建操作，有副作用）
    路径参数：package_name - 包名称
    请求体（可选）：
        {
            "github_token": "...",      // 可选
            "repo_owner": "...",        // 可选
            "repo_name": "...",         // 可选
            "base_branch": "...",       // 可选
            "branch_prefix": "..."      // 可选
        }
    返回：PR 创建结果
    """
    # 如果没有提供请求体，使用默认值
    if request is None:
        request = PRRequest()

    logger.info(f"[API] Received PR creation request for {package_name}")

    try:
        # 设置触发源为 API
        from .database import set_trigger_source
        set_trigger_source("api")

        # 加载 riko 数据（确保能找到 manifest）
        riko = get_riko()
        riko.load_from_cache()

        # 构建命令参数对象
        from argparse import Namespace

        args = Namespace(
            package_name=package_name,
            github_token=request.github_token,
            repo_owner=request.repo_owner,
            repo_name=request.repo_name,
            base_branch=request.base_branch,
            branch_prefix=request.branch_prefix
        )

        # 直接调用 PR 创建命令
        pr_command(args)

        # 从数据库获取 PR 创建结果
        from .database import get_database
        from .database.models import PRRecord

        db = get_database()
        result = None

        with db.get_session() as session:
            pr_record = session.query(PRRecord).filter(
                PRRecord.package_name == package_name
            ).order_by(PRRecord.created_at.desc()).first()

            if pr_record:
                # 在 session 内部提取数据（避免会话关闭后访问属性）
                result = {
                    "package_name": pr_record.package_name,
                    "version": pr_record.version,
                    "status": pr_record.status,
                    "pr_number": pr_record.pr_number,
                    "pr_url": pr_record.pr_url,
                    "branch_name": pr_record.branch_name,
                    "error_type": pr_record.error_type,
                    "error_message": pr_record.error_message
                }

        if result:
            return result
        else:
            raise HTTPException(status_code=500, detail="Failed to retrieve PR record")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] PR creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 调度器管理
@app.post("/scheduler/start")
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
        from .database import set_trigger_source
        set_trigger_source("api")

        start_scheduler(request.hour, request.minute)
        return {
            "message": f"Scheduler started, will run daily at {request.hour:02d}:{request.minute:02d}",
            "status": scheduler_status()
        }
    except Exception as e:
        logger.error(f"[API] Failed to start scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scheduler/stop")
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


@app.get("/scheduler/status")
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


@app.post("/scheduler/trigger")
def api_trigger_daily_check():
    """
    手动触发每日检查和 PR 任务

    HTTP 方法：POST（触发操作）
    返回：执行结果
    """
    logger.info("[API] Triggering daily check")

    try:
        # 设置触发源为 API
        from .database import set_trigger_source
        set_trigger_source("api")

        daily_check_and_pr()
        return {
            "message": "Daily check and PR task triggered",
            "status": scheduler_status()
        }
    except Exception as e:
        logger.error(f"[API] Failed to trigger daily check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 启动服务器
if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Riko API server...")
    uvicorn.run(
        app=app,
        host="localhost",
        port=7777
    )
    logger.info("API server stopped")
