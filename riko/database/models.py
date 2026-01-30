# riko/database/models_v2.py - 简化的数据库模型设计
"""
简化设计原则：
1. 所有 manifest 生成记录统一存储在 manifest_records 表
2. 用 status 字段表示成功/失败/跳过
3. 失败信息直接记录在 manifest_records 中，不需要单独的 failure_records 表
4. 保留 scan_records 和 package_updates 表作为上下文
"""

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


# ========== Base 类 ==========
class Base(DeclarativeBase):
    """所有模型的基类"""
    pass

# ========== 1. 扫描记录表 ==========
class ScanRecord(Base):
    """
    扫描记录表 - 保持不变
    记录每次扫描的整体信息
    """
    __tablename__ = 'scan_records'
    __table_args__ = (
        CheckConstraint("scan_type IN ('manual', 'scheduled')", name='chk_scan_type'),
        Index('idx_scan_records_time', 'scan_time'),
        Index('idx_scan_records_status', 'status'),
    )

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 扫描基本信息
    scan_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    scan_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'manual' / 'scheduled'
    trigger_source: Mapped[Optional[str]] = mapped_column(String(50))  # 'scheduler' / 'cli' / 'api'

    # 扫描状态
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # 'running' / 'completed' / 'failed' / 'partial_failed'
    total_packages: Mapped[int] = mapped_column(Integer, default=0)
    updated_packages: Mapped[int] = mapped_column(Integer, default=0)
    success_packages: Mapped[int] = mapped_column(Integer, default=0)
    failed_packages: Mapped[int] = mapped_column(Integer, default=0)

    # 时间统计
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)

    # 元数据（JSON 格式）
    error_summary: Mapped[Optional[str]] = mapped_column(Text)  # JSON 字符串
    meta_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON 字符串

    # 关系
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

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 外键
    scan_id: Mapped[int] = mapped_column(Integer, ForeignKey('scan_records.id'), nullable=False)

    # 包信息
    package_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # 版本信息
    old_version: Mapped[Optional[str]] = mapped_column(String(100))
    new_version: Mapped[str] = mapped_column(String(100), nullable=False)

    # 版本检查状态
    check_status: Mapped[str] = mapped_column(String(50), nullable=False)  # 'updated' / 'up-to-date' / 'error' / 'no-result'
    check_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # nvchecker 信息
    nvchecker_event: Mapped[Optional[str]] = mapped_column(String(50))
    nvchecker_url: Mapped[Optional[str]] = mapped_column(Text)

    # 元数据（JSON 格式）
    meta_data: Mapped[Optional[str]] = mapped_column(Text)

    # 关系
    scan: Mapped["ScanRecord"] = relationship("ScanRecord", back_populates="package_updates")

    def set_metadata(self, data: Dict[str, Any]) -> None:
        """设置元数据"""
        self.meta_data = json.dumps(data)

    def get_metadata(self) -> Dict[str, Any]:
        """获取元数据"""
        return json.loads(self.meta_data) if self.meta_data else {}

    def __repr__(self) -> str:
        return f"<PackageUpdate(id={self.id}, package={self.package_name}, {self.old_version}→{self.new_version})>"


# ========== 3. Manifest 生成记录表 ==========
class ManifestRecord(Base):
    """
    Manifest 生成记录表 - 简化设计

    统一记录所有 manifest 生成尝试（成功/失败/跳过）
    不再需要单独的 failure_records 表来记录 manifest 失败
    """
    __tablename__ = 'manifest_records'
    __table_args__ = (
        Index('idx_manifest_records_scan', 'scan_id'),
        Index('idx_manifest_records_package', 'package_name'),
        Index('idx_manifest_records_status', 'status'),
        Index('idx_manifest_records_time', 'created_at'),
    )

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 外键
    scan_id: Mapped[int] = mapped_column(Integer, ForeignKey('scan_records.id'), nullable=False)

    # 包信息
    package_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    combo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)

    # ========== 生成状态（简化设计） ==========
    # 使用统一的 status 字段，而不是 success/skipped/failed 三个状态
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )  # 'success' / 'failed' / 'skipped'

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # ========== 成功时的字段 ==========
    # 只有当 status='success' 时这些字段才有值
    manifest_path: Mapped[Optional[str]] = mapped_column(Text)  # 生成的 manifest 文件路径
    manifest_size: Mapped[Optional[int]] = mapped_column(Integer)  # 文件大小（字节）
    manifest_hash: Mapped[Optional[str]] = mapped_column(String(64))  # sha256

    # ========== 失败时的字段 ==========
    # 只有当 status='failed' 时这些字段才有值
    error_type: Mapped[Optional[str]] = mapped_column(String(100))  # 错误类型：HTTPError, ValueError, AssertionError
    error_message: Mapped[Optional[str]] = mapped_column(Text)  # 错误消息
    error_code: Mapped[Optional[int]] = mapped_column(Integer)  # HTTP 状态码：404, 500 等
    error_details: Mapped[Optional[str]] = mapped_column(Text)  # JSON 格式的详细信息（堆栈跟踪等）

    # ========== 跳过时的原因 ==========
    # 只有当 status='skipped' 时这个字段才有值
    skip_reason: Mapped[Optional[str]] = mapped_column(String(255))  # 跳过原因：'keep_back', 'already_exists', 'policy'

    # 元数据（JSON 格式）
    meta_data: Mapped[Optional[str]] = mapped_column(Text)

    # 关系
    scan: Mapped["ScanRecord"] = relationship("ScanRecord", back_populates="manifests")

    def set_metadata(self, data: Dict[str, Any]) -> None:
        """设置元数据"""
        self.meta_data = json.dumps(data)

    def get_metadata(self) -> Dict[str, Any]:
        """获取元数据"""
        return json.loads(self.meta_data) if self.meta_data else {}

    def set_error_details(self, data: Dict[str, Any]) -> None:
        """设置错误详情"""
        self.error_details = json.dumps(data)

    def get_error_details(self) -> Dict[str, Any]:
        """获取错误详情"""
        return json.loads(self.error_details) if self.error_details else {}

    @hybrid_property
    def is_success(self) -> bool:
        """是否成功"""
        return self.status == 'success'

    @hybrid_property
    def is_failed(self) -> bool:
        """是否失败"""
        return self.status == 'failed'

    @hybrid_property
    def is_skipped(self) -> bool:
        """是否跳过"""
        return self.status == 'skipped'

    def __repr__(self) -> str:
        return f"<ManifestRecord(id={self.id}, package={self.package_name}, combo={self.combo_name}, status={self.status})>"


# ========== 4. PR 创建记录表 ==========
class PRRecord(Base):
    """
    PR 创建记录表 - 简化设计

    统一记录所有 PR 创建尝试（成功/失败/跳过）
    """
    __tablename__ = 'pr_records'
    __table_args__ = (
        Index('idx_pr_records_scan', 'scan_id'),
        Index('idx_pr_records_package', 'package_name'),
        Index('idx_pr_records_status', 'status'),
        Index('idx_pr_records_time', 'created_at'),
    )

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 外键
    scan_id: Mapped[int] = mapped_column(Integer, ForeignKey('scan_records.id'), nullable=False)
    manifest_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey('manifest_records.id'), nullable=True
    )

    # PR 信息
    package_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)

    # ========== 创建状态（简化设计） ==========
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )  # 'success' / 'failed' / 'skipped'

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # ========== 成功时的字段 ==========
    # 只有当 status='success' 时这些字段才有值
    repo_owner: Mapped[Optional[str]] = mapped_column(String(100))  # 仓库所有者
    repo_name: Mapped[Optional[str]] = mapped_column(String(100))  # 仓库名称
    pr_number: Mapped[Optional[int]] = mapped_column(Integer)  # PR 编号
    pr_url: Mapped[Optional[str]] = mapped_column(Text)  # PR URL
    branch_name: Mapped[Optional[str]] = mapped_column(String(255))  # 功能分支名

    # ========== 失败时的字段 ==========
    # 只有当 status='failed' 时这些字段才有值
    error_type: Mapped[Optional[str]] = mapped_column(String(100))  # 错误类型
    error_message: Mapped[Optional[str]] = mapped_column(Text)  # 错误消息
    error_details: Mapped[Optional[str]] = mapped_column(Text)  # JSON 格式的详细信息

    # ========== 跳过时的原因 ==========
    # 只有当 status='skipped' 时这个字段才有值
    skip_reason: Mapped[Optional[str]] = mapped_column(String(255))  # 跳过原因

    # 元数据（JSON 格式）
    meta_data: Mapped[Optional[str]] = mapped_column(Text)

    # 关系
    scan: Mapped["ScanRecord"] = relationship("ScanRecord", back_populates="prs")
    manifest: Mapped[Optional["ManifestRecord"]] = relationship("ManifestRecord")

    def set_metadata(self, data: Dict[str, Any]) -> None:
        """设置元数据"""
        self.meta_data = json.dumps(data)

    def get_metadata(self) -> Dict[str, Any]:
        """获取元数据"""
        return json.loads(self.meta_data) if self.meta_data else {}

    def set_error_details(self, data: Dict[str, Any]) -> None:
        """设置错误详情"""
        self.error_details = json.dumps(data)

    def get_error_details(self) -> Dict[str, Any]:
        """获取错误详情"""
        return json.loads(self.error_details) if self.error_details else {}

    @hybrid_property
    def full_repo_name(self) -> Optional[str]:
        """获取完整的仓库名称"""
        if self.repo_owner and self.repo_name:
            return f"{self.repo_owner}/{self.repo_name}"
        return None

    def __repr__(self) -> str:
        return f"<PRRecord(id={self.id}, package={self.package_name}, status={self.status})>"
