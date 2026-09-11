#!/usr/bin/env python3

import logging

from fastapi import FastAPI
from .routes import check_routes, manifest_routes, pr_routes, scheduler_routes, telegramBot_routes, versions_sync_routes

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Ruyi Packaging API",
    version="0.2.0",
    description="Riko package management and automation API"
)

app.include_router(check_routes.router)
app.include_router(manifest_routes.router)
app.include_router(pr_routes.router)
app.include_router(scheduler_routes.router)
app.include_router(telegramBot_routes.router)
app.include_router(versions_sync_routes.router)


@app.get("/")
def api_root():
    return {
        "name": "Riko API",
        "version": "0.2.0",
        "description": "Riko package management and automation API",
        "endpoints": {
            "check": {
                "GET /check": "get version check results",
                "POST /check/run": "run version check"
            },
            "manifests": {
                "POST /manifests/{package_name}": "generate manifests for a package"
            },
            "pr": {
                "POST /pr/{package_name}": "create a PR for a package"
            },
            "scheduler": {
                "POST /scheduler/start": "start the scheduler",
                "POST /scheduler/stop": "stop the scheduler",
                "GET /scheduler/status": "get scheduler status",
                "POST /scheduler/trigger": "manually trigger the daily check and PR task"
            },
            "telegram": {
                "POST /telegram/report": "submit package results as one Telegram summary"
            },
            "versions-sync": {
                "POST /version-sync": "run version sync (compare upstream versions and create a PR)"
            }
        }
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Riko API server...")
    uvicorn.run(
        app=app,
        host="localhost",
        port=7777
    )
    logger.info("API server stopped")
