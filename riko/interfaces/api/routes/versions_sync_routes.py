#!/usr/bin/env python3
"""
Version Sync Routes for the Riko API

Provides endpoints for version synchronization operations.
"""

import logging
from argparse import Namespace
from typing import Optional
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from ..models.schemas import VersionSyncRequest,VersionSyncResponse

from ...cli.version_sync import version_sync as version_sync_command
from ....core import get_riko
from ....database import set_trigger_source, get_database
from ....database.models import ScanRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/version-sync", tags=["version-sync"])




@router.post("", response_model=VersionSyncResponse)
def api_version_sync(
    request: VersionSyncRequest = Body(default=None)
):
    if request is None:
        request = VersionSyncRequest()

    logger.info(f"[API] Received version-sync request (dry_run={request.dry_run}, package={request.package})")

    try:
        set_trigger_source("api")

        riko = get_riko()
        riko.load_from_cache()

        args = Namespace(
            dry_run=request.dry_run,
            package=request.package,
            verbose=request.verbose,
            github_token=request.github_token,
            repo_owner=request.repo_owner,
            repo_name=request.repo_name,
            base_branch=request.base_branch,
            branch_prefix=request.branch_prefix
        )

        version_sync_command(args)

        db = get_database()
        result = None

        with db.get_session() as session:
            scan_record = session.query(ScanRecord).filter(
                ScanRecord.scan_type == "manual"
            ).order_by(ScanRecord.id.desc()).first()

            if scan_record:
                result = {
                    "status": scan_record.status,
                    "packages_scanned": scan_record.total_packages or 0,
                    "combos_with_changes": 0,
                    "versions_to_add": 0,
                    "versions_to_delete": 0,
                    "scan_id": scan_record.id,
                    "error_type": scan_record.error_type,
                    "error_message": scan_record.error_message
                }

        if result:
            return result
        else:
            raise HTTPException(status_code=500, detail="Failed to retrieve scan record")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] version-sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
