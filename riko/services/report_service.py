"""Build normalized package reports from API input and Riko-managed data."""

from typing import Iterable, Optional

from ..core import get_riko
from ..core.report_models import PackageReportData
from ..database import get_database
from ..database.models import ManifestRecord, PRRecord

class PackageReportService:
    """Enrich external package results without assuming any package identity."""

    @staticmethod
    def _build_report(
        request,
        *,
        riko,
        database=None,
    ) -> PackageReportData:
        package_config = riko.get_ruyi_package(request.package)
        nvchecker_result = riko.get_nvchecker_result(request.package) or {}

        old_version = (
            request.old_version
            if request.old_version is not None
            else nvchecker_result.get("old_version")
        )
        new_version = request.new_version
        if new_version is None:
            new_version = nvchecker_result.get("version")
        if new_version is None:
            new_version = nvchecker_result.get("new_version")

        manifest_status = request.manifest_status
        pr_status = request.pr_status
        pr_url = request.pr_url

        if new_version is not None and (
            manifest_status is None or pr_status is None or pr_url is None
        ):
            database = database or get_database()
            fallback = PackageReportService._database_fallback(
                database, request.package, new_version
            )
            if manifest_status is None:
                manifest_status = fallback["manifest_status"]
            if pr_status is None:
                pr_status = fallback["pr_status"]
            if pr_url is None:
                pr_url = fallback["pr_url"]

        return PackageReportData(
            package=request.package,
            package_config_found=package_config is not None,
            category=package_config.get_category() if package_config else None,
            nvchecker=dict(package_config.get_nvchecker_dat()) if package_config else None,
            source=dict(package_config.get_source()) if package_config else None,
            combos=list(package_config.get_combos()) if package_config else [],
            policies=dict(package_config.get_policies()) if package_config else None,
            old_version=old_version,
            new_version=new_version,
            status=request.status,
            message=request.message,
            manifest_status=manifest_status,
            pr_status=pr_status,
            pr_url=pr_url,
            details=dict(request.details),
        )

    @staticmethod
    def build_reports(requests, *, riko=None, database=None) -> list[PackageReportData]:
        """Load Riko's cache once, then enrich every report in the request."""
        riko = riko or get_riko()
        riko.load_from_cache()
        return [
            PackageReportService._build_report(
                request,
                riko=riko,
                database=database,
            )
            for request in requests
        ]

    @staticmethod
    def _database_fallback(database, package: str, version: str) -> dict:
        result = {"manifest_status": None, "pr_status": None, "pr_url": None}

        try:
            with database.get_session() as session:
                manifest_records = (
                    session.query(ManifestRecord)
                    .filter(
                        ManifestRecord.package_name == package,
                        ManifestRecord.version == version,
                    )
                    .order_by(ManifestRecord.created_at.desc(), ManifestRecord.id.desc())
                    .all()
                )
                latest_status_by_combo = {}
                for record in manifest_records:
                    latest_status_by_combo.setdefault(record.combo_name, record.status)
                result["manifest_status"] = PackageReportService._aggregate_manifest_status(
                    latest_status_by_combo.values()
                )

                pr_record = (
                    session.query(PRRecord)
                    .filter(
                        PRRecord.package_name == package,
                        PRRecord.version == version,
                    )
                    .order_by(PRRecord.created_at.desc(), PRRecord.id.desc())
                    .first()
                )
                if pr_record is not None:
                    result["pr_status"] = pr_record.status
                    result["pr_url"] = pr_record.pr_url
        except Exception as exc:
            logger.warning(
                "Could not enrich package report from database for %s/%s: %s",
                package,
                version,
                exc,
            )

        return result

    @staticmethod
    def _aggregate_manifest_status(statuses: Iterable[str]) -> Optional[str]:
        values = list(statuses)
        if not values:
            return None
        if "failed" in values:
            return "failed"
        if all(status == "success" for status in values):
            return "success"
        if len(set(values)) == 1:
            return values[0]
        return "partial"
