"""Domain model for normalized external package reports."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PackageReportData(BaseModel):
    """Complete report data before presentation-specific formatting."""

    package: str
    package_config_found: bool
    category: Optional[str] = None
    nvchecker: Optional[Dict[str, Any]] = None
    source: Optional[Dict[str, Any]] = None
    combos: List[str] = Field(default_factory=list)
    policies: Optional[Dict[str, Any]] = None
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    status: str
    message: Optional[str] = None
    manifest_status: Optional[str] = None
    pr_status: Optional[str] = None
    pr_url: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
