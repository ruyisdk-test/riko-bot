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
