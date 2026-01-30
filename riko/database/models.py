# riko/database/models.py - 数据库模型

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String, Integer, DateTime, Boolean, Text, ForeignKey, CheckConstraint,
    Index, UniqueConstraint
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship,
)
from sqlalchemy.ext.hybrid import hybrid_property
import json


class Base(DeclarativeBase):
    pass


class ScanRecord(Base):
    __tablename__ = 'scan_records'
    __table_args__ = (
        CheckConstraint("scan_type IN ('manual', 'scheduled')", name='chk_scan_type'),
        Index('idx_scan_records_time', 'scan_time'),
        Index('idx_scan_records_status', 'status'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scan_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    scan_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_source: Mapped[Optional[str]] = mapped_column(String(50))

    status: Mapped[str] = mapped_column(String(50), nullable=False)
    total_packages: Mapped[int] = mapped_column(Integer, default=0)
    updated_packages: Mapped[int] = mapped_column(Integer, default=0)
    success_packages: Mapped[int] = mapped_column(Integer, default=0)
    failed_packages: Mapped[int] = mapped_column(Integer, default=0)

    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)

    error_summary: Mapped[Optional[str]] = mapped_column(Text)
    meta_data: Mapped[Optional[str]] = mapped_column(Text)

    package_updates: Mapped[List["PackageUpdate"]] = relationship(
        "PackageUpdate", back_populates="scan", cascade="all, delete-orphan"
    )
    manifests: Mapped[List["ManifestRecord"]] = relationship(
        "ManifestRecord", back_populates="scan", cascade="all, delete-orphan"
    )
    prs: Mapped[List["PRRecord"]] = relationship(
        "PRRecord", back_populates="scan", cascade="all, delete-orphan"
    )

    def set_metadata(self, data: Dict[str, Any]) -> None:
        """设置元数据"""
        self.meta_data = json.dumps(data)

    def get_metadata(self) -> Dict[str, Any]:
        """获取元数据"""
        return json.loads(self.meta_data) if self.meta_data else {}

    def __repr__(self) -> str:
        return f"<ScanRecord(id={self.id}, scan_time={self.scan_time}, status={self.status})>"


# ========== 2. 包更新记录表 ==========
class PackageUpdate(Base):
    """
    包更新记录表 - 保持不变
    记录每个包的版本检查结果
    """
    __tablename__ = 'package_updates'
    __table_args__ = (
        Index('idx_package_updates_scan', 'scan_id'),
        Index('idx_package_updates_name', 'package_name'),
        Index('idx_package_updates_status', 'check_status'),
        Index('idx_package_updates_time', 'check_time'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scan_id: Mapped[int] = mapped_column(Integer, ForeignKey('scan_records.id'), nullable=False)

    package_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    old_version: Mapped[Optional[str]] = mapped_column(String(100))
    new_version: Mapped[str] = mapped_column(String(100), nullable=False)

    check_status: Mapped[str] = mapped_column(String(50), nullable=False)
    check_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    nvchecker_event: Mapped[Optional[str]] = mapped_column(String(50))
    nvchecker_url: Mapped[Optional[str]] = mapped_column(Text)

    meta_data: Mapped[Optional[str]] = mapped_column(Text)

    scan: Mapped["ScanRecord"] = relationship("ScanRecord", back_populates="package_updates")

    def set_metadata(self, data: Dict[str, Any]) -> None:
        self.meta_data = json.dumps(data)

    def get_metadata(self) -> Dict[str, Any]:
        return json.loads(self.meta_data) if self.meta_data else {}

    def __repr__(self) -> str:
        return f"<PackageUpdate(id={self.id}, package={self.package_name}, {self.old_version}→{self.new_version})>"


class ManifestRecord(Base):
    __tablename__ = 'manifest_records'
    __table_args__ = (
        Index('idx_manifest_records_scan', 'scan_id'),
        Index('idx_manifest_records_package', 'package_name'),
        Index('idx_manifest_records_status', 'status'),
        Index('idx_manifest_records_time', 'created_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scan_id: Mapped[int] = mapped_column(Integer, ForeignKey('scan_records.id'), nullable=False)

    package_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    combo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    manifest_path: Mapped[Optional[str]] = mapped_column(Text)
    manifest_size: Mapped[Optional[int]] = mapped_column(Integer)
    manifest_hash: Mapped[Optional[str]] = mapped_column(String(64))

    error_type: Mapped[Optional[str]] = mapped_column(String(100))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_code: Mapped[Optional[int]] = mapped_column(Integer)
    error_details: Mapped[Optional[str]] = mapped_column(Text)

    skip_reason: Mapped[Optional[str]] = mapped_column(String(255))

    meta_data: Mapped[Optional[str]] = mapped_column(Text)

    scan: Mapped["ScanRecord"] = relationship("ScanRecord", back_populates="manifests")

    def set_metadata(self, data: Dict[str, Any]) -> None:
        self.meta_data = json.dumps(data)

    def get_metadata(self) -> Dict[str, Any]:
        return json.loads(self.meta_data) if self.meta_data else {}

    def set_error_details(self, data: Dict[str, Any]) -> None:
        self.error_details = json.dumps(data)

    def get_error_details(self) -> Dict[str, Any]:
        return json.loads(self.error_details) if self.error_details else {}

    @hybrid_property
    def is_success(self) -> bool:
        return self.status == 'success'

    @hybrid_property
    def is_failed(self) -> bool:
        return self.status == 'failed'

    @hybrid_property
    def is_skipped(self) -> bool:
        return self.status == 'skipped'

    def __repr__(self) -> str:
        return f"<ManifestRecord(id={self.id}, package={self.package_name}, combo={self.combo_name}, status={self.status})>"


class PRRecord(Base):
    __tablename__ = 'pr_records'
    __table_args__ = (
        Index('idx_pr_records_scan', 'scan_id'),
        Index('idx_pr_records_package', 'package_name'),
        Index('idx_pr_records_status', 'status'),
        Index('idx_pr_records_time', 'created_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scan_id: Mapped[int] = mapped_column(Integer, ForeignKey('scan_records.id'), nullable=False)
    manifest_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey('manifest_records.id'), nullable=True
    )

    package_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    repo_owner: Mapped[Optional[str]] = mapped_column(String(100))
    repo_name: Mapped[Optional[str]] = mapped_column(String(100))
    pr_number: Mapped[Optional[int]] = mapped_column(Integer)
    pr_url: Mapped[Optional[str]] = mapped_column(Text)
    branch_name: Mapped[Optional[str]] = mapped_column(String(255))

    error_type: Mapped[Optional[str]] = mapped_column(String(100))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_details: Mapped[Optional[str]] = mapped_column(Text)

    skip_reason: Mapped[Optional[str]] = mapped_column(String(255))

    meta_data: Mapped[Optional[str]] = mapped_column(Text)

    scan: Mapped["ScanRecord"] = relationship("ScanRecord", back_populates="prs")
    manifest: Mapped[Optional["ManifestRecord"]] = relationship("ManifestRecord")

    def set_metadata(self, data: Dict[str, Any]) -> None:
        self.meta_data = json.dumps(data)

    def get_metadata(self) -> Dict[str, Any]:
        return json.loads(self.meta_data) if self.meta_data else {}

    def set_error_details(self, data: Dict[str, Any]) -> None:
        self.error_details = json.dumps(data)

    def get_error_details(self) -> Dict[str, Any]:
        return json.loads(self.error_details) if self.error_details else {}

    @hybrid_property
    def full_repo_name(self) -> Optional[str]:
        if self.repo_owner and self.repo_name:
            return f"{self.repo_owner}/{self.repo_name}"
        return None

    def __repr__(self) -> str:
        return f"<PRRecord(id={self.id}, package={self.package_name}, status={self.status})>"
