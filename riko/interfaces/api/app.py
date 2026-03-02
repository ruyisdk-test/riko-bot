#!/usr/bin/env python3
# riko/interfaces/api/app.py - FastAPI Web 服务
"""
提供 HTTP API 接口来调用 riko 的各个功能

直接调用项目内部方法，不使用 subprocess
"""

import logging

from fastapi import FastAPI
from .routes import check_routes, manifest_routes, pr_routes, scheduler_routes, versions_sync_routes

logger = logging.getLogger(__name__)

# 初始化 FastAPI 应用
app = FastAPI(
    title="Ruyi Packaging API",
    version="0.2.0",
    description="Riko 包管理和自动化工具 API"
)

# 注册路由
app.include_router(check_routes.router)
app.include_router(manifest_routes.router)
app.include_router(pr_routes.router)
app.include_router(scheduler_routes.router)
app.include_router(versions_sync_routes.router)

# 根路径
@app.get("/")
def api_root():
    """API 根路径，返回可用端点列表"""
    return {
        "name": "Riko API",
        "version": "0.2.0",
        "description": "Riko 包管理和自动化工具 API",
        "endpoints": {
            "check": {
                "GET /check": "获取版本检查结果",
                "POST /check/run": "执行版本检查"
            },
            "manifests": {
                "POST /manifests/{package_name}": "生成指定包的 Manifest"
            },
            "pr": {
                "POST /pr/{package_name}": "为指定包创建 PR"
            },
            "scheduler": {
                "POST /scheduler/start": "启动定时调度器",
                "POST /scheduler/stop": "停止定时调度器",
                "GET /scheduler/status": "获取调度器状态",
                "POST /scheduler/trigger": "手动触发每日检查和 PR 任务"
            },
            "versions-sync": {
                "POST /version-sync": "执行版本同步（对比上游版本并创建 PR）"
            }
        }
    }


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
