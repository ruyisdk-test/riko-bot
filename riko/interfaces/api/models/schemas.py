"""
Pydantic models for the Riko API

This module contains all request and response schemas used by the API endpoints.
"""

from pydantic import BaseModel
from typing import Optional, List


# Check Endpoints Models

class CheckResponse(BaseModel):
    """版本检查响应"""
    total: int
    updated: int
    up_to_date: int
    errors: int
    packages: List[dict]


# Manifests Endpoints Models

class ManifestsRequest(BaseModel):
    """Manifest 生成请求"""
    versions: Optional[List[str]] = None  # 要生成的版本列表
    down_grade: bool = False  # 是否降级生成


class ManifestsResponse(BaseModel):
    """Manifest 生成响应"""
    package_name: str
    combo_name: str
    version: str
    status: str  # success / failed / skipped
    manifest_path: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


# PR Endpoints Models

class PRRequest(BaseModel):
    """PR 创建请求"""
    branch_prefix: Optional[str] = None
    github_token: Optional[str] = None
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    base_branch: Optional[str] = None


# Scheduler Endpoints Models

class SchedulerStartRequest(BaseModel):
    """调度器启动请求（暂未使用，默认为每天凌晨2点）"""
    # 注：当前 scheduler.py 硬编码为每天凌晨2点，此参数暂未生效
    hour: int = 2
    minute: int = 0

# versions-sync Endpoints Models
class VersionSyncRequest(BaseModel):
    """版本同步请求"""
    dry_run: bool = False  # 预览模式，不执行实际修改
    package: Optional[str] = None  # 指定单个包
    verbose: bool = False  # 详细输出模式
    github_token: Optional[str] = None  # GitHub Token
    repo_owner: Optional[str] = None  # 仓库所有者
    repo_name: Optional[str] = None  # 仓库名称
    base_branch: Optional[str] = None  # 基础分支
    branch_prefix: Optional[str] = None  # 分支前缀


class VersionSyncResponse(BaseModel):
    """版本同步响应"""
    status: str  # success / failed / dry_run
    packages_scanned: int  # 扫描的包数量
    combos_with_changes: int  # 有变更的 combo 数量
    versions_to_add: int  # 要添加的版本数
    versions_to_delete: int  # 要删除的版本数
    scan_id: Optional[int] = None  # 扫描记录 ID
    error_type: Optional[str] = None
    error_message: Optional[str] = None