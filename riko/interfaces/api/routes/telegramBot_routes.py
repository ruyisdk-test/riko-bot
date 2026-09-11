"""Telegram package report endpoint for external test and processing results."""

import logging

from fastapi import APIRouter, HTTPException

from ..models.schemas import (
    TelegramReportRequest,
    TelegramReportResponse,
)
from ....services.report_service import PackageReportService
from ....services import telegramBot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/report", response_model=TelegramReportResponse)
async def telegram_report(request: TelegramReportRequest) -> TelegramReportResponse:
    reports = PackageReportService.build_reports(request.reports)
    telegram_sent = await telegramBot_service.notify_package_reports(reports)

    if not telegram_sent:
        logger.error(
            "Telegram notification failed for reports: %s",
            [{"package": report.package, "status": report.status} for report in reports],
        )
        raise HTTPException(status_code=503, detail="Telegram notification failed")

    success_count = sum(report.status == "success" for report in reports)
    failed_count = sum(report.status == "failed" for report in reports)
    skipped_count = sum(report.status == "skipped" for report in reports)
    return TelegramReportResponse(
        success=True,
        telegram_sent=True,
        total=len(reports),
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        results=reports,
    )
