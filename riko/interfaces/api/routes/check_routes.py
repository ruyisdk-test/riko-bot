"""
Check routes for the Riko API

Provides endpoints for version checking operations.
"""

import logging
from fastapi import APIRouter, HTTPException

from ..models.schemas import CheckResponse
from ...cli.check import check as check_command
from ....core import get_riko
from ....database import set_trigger_source

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/check", tags=["check"])


@router.get("", response_model=CheckResponse)
@router.get("/", response_model=CheckResponse)
def api_check_versions():
    logger.info("[API] Received check request")

    try:
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


@router.post("/run", response_model=CheckResponse)
def api_run_check():
    logger.info("[API] Received check run request")

    try:
        set_trigger_source("api")

        check_command()

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
