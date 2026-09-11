"""
Pydantic models for the Riko API

This module contains all request and response schemas used by the API endpoints.
"""

from pydantic import BaseModel, ConfigDict, Field, constr
from typing import Any, Dict, List, Literal, Optional

from ....core.report_models import PackageReportData

NonBlankString = constr(strip_whitespace=True, min_length=1)


# Check Endpoints Models

class CheckResponse(BaseModel):
    """Version check response."""
    total: int
    updated: int
    up_to_date: int
    errors: int
    packages: List[dict]


# Manifests Endpoints Models

class ManifestsRequest(BaseModel):
    """Manifest generation request."""
    versions: Optional[List[str]] = None
    down_grade: bool = False


class ManifestsResponse(BaseModel):
    """Manifest generation response."""
    package_name: str
    combo_name: str
    version: str
    status: str  # success / failed / skipped
    manifest_path: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


# PR Endpoints Models

class PRRequest(BaseModel):
    """PR creation request."""
    branch_prefix: Optional[str] = None
    github_token: Optional[str] = None
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    base_branch: Optional[str] = None


# Scheduler Endpoints Models

class SchedulerStartRequest(BaseModel):
    """Scheduler start request (unused for now; defaults to 2 AM daily)."""
    # NOTE: scheduler.py currently hardcodes 2 AM; this field is not yet effective
    hour: int = 2
    minute: int = 0

# versions-sync Endpoints Models
class VersionSyncRequest(BaseModel):
    """Version sync request."""
    dry_run: bool = False
    package: Optional[str] = None
    verbose: bool = False
    github_token: Optional[str] = None
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    base_branch: Optional[str] = None
    branch_prefix: Optional[str] = None


class VersionSyncResponse(BaseModel):
    """Version sync response."""
    status: str  # success / failed / dry_run
    packages_scanned: int
    combos_with_changes: int
    versions_to_add: int
    versions_to_delete: int
    scan_id: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


# Telegram Package Report Models

ReportStatus = Literal["success", "failed", "skipped"]


class TelegramReportItem(BaseModel):
    """External package result submitted for Telegram notification."""
    model_config = ConfigDict(extra="forbid")

    package: NonBlankString
    status: ReportStatus
    message: Optional[str] = None
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    manifest_status: Optional[str] = None
    pr_status: Optional[str] = None
    pr_url: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class TelegramReportRequest(BaseModel):
    """One or more package reports to send in a single notification."""
    model_config = ConfigDict(extra="forbid")

    reports: List[TelegramReportItem] = Field(min_length=1)


class TelegramReportResponse(BaseModel):
    """Result of building and sending package reports."""
    success: bool
    telegram_sent: bool
    total: int
    success_count: int
    failed_count: int
    skipped_count: int
    results: List[PackageReportData]
