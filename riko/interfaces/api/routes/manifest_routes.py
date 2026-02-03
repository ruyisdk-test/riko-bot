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
        db = get_database()
        results = []

        with db.get_session() as session:
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
