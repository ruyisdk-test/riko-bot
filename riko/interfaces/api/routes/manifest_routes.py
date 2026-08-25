"""
Manifest routes for the Riko API

Provides endpoints for manifest generation operations.
"""

import logging
from argparse import Namespace
from fastapi import APIRouter, HTTPException, Body

from ..models.schemas import ManifestsRequest, ManifestsResponse
from ...cli.manifests import manifests as manifests_command
from ....core import get_riko
from ....database import set_trigger_source, get_database
from ....database.models import ManifestRecord
from sqlalchemy import desc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/manifests", tags=["manifests"])


@router.post("/{package_name}")
def api_generate_manifests(
    package_name: str,
    request: ManifestsRequest = Body(default=None)
):
    if request is None:
        request = ManifestsRequest()

    logger.info(f"[API] Received manifests request for {package_name}: {request}")

    try:
        set_trigger_source("api")

        riko = get_riko()
        riko.load_from_cache()

        gen_vers = request.versions if request.versions else []
        down_grade = request.down_grade

        manifests_command(package_name, gen_vers, down_grade)

        db = get_database()
        results = []

        with db.get_session() as session:
            manifest_records = session.query(ManifestRecord).filter(
                ManifestRecord.package_name == package_name
            ).order_by(desc(ManifestRecord.created_at)).limit(50).all()

            # convert inside the session to avoid detached attribute access
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
