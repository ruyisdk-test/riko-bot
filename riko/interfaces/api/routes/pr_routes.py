"""
PR routes for the Riko API

Provides endpoints for pull request creation operations.
"""

import logging
from argparse import Namespace
from fastapi import APIRouter, HTTPException, Body

from ..models.schemas import PRRequest
from ...cli.pr import pr as pr_command
from ....core import get_riko
from ....database import set_trigger_source, get_database
from ....database.models import PRRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pr", tags=["pr"])


@router.post("/{package_name}")
def api_create_pr(
    package_name: str,
    request: PRRequest = Body(default=None)
):
    if request is None:
        request = PRRequest()

    logger.info(f"[API] Received PR creation request for {package_name}")

    try:
        set_trigger_source("api")

        riko = get_riko()
        riko.load_from_cache()

        args = Namespace(
            package_name=package_name,
            github_token=request.github_token,
            repo_owner=request.repo_owner,
            repo_name=request.repo_name,
            base_branch=request.base_branch,
            branch_prefix=request.branch_prefix
        )

        pr_command(args)

        db = get_database()
        result = None

        with db.get_session() as session:
            pr_record = session.query(PRRecord).filter(
                PRRecord.package_name == package_name
            ).order_by(PRRecord.created_at.desc()).first()

            if pr_record:
                # extract inside the session to avoid detached attribute access
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
