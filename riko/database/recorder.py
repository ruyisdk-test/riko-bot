#!/usr/bin/env python3
# riko/database/recorder.py - 统一数据库记录工具
"""
为所有 CLI 命令提供数据库记录功能

使用装饰器模式，自动记录命令执行过程
"""

import logging
import functools
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from traceback import format_exception
from contextvars import ContextVar

from .db_manager import get_database
from .models import ScanRecord, PackageUpdate, ManifestRecord, PRRecord

logger = logging.getLogger(__name__)

# 触发源上下文
# 使用 ContextVar 来存储当前请求的触发源（线程安全）
_trigger_source_context: ContextVar[str] = ContextVar('trigger_source', default='cli')


def set_trigger_source(source: str) -> None:
    """设置触发源上下文"""
    _trigger_source_context.set(source)


def get_trigger_source() -> str:
    """获取当前触发源"""
    return _trigger_source_context.get()


# 统一记录器
class CommandRecorder:
    """
    命令执行记录器

    为所有 CLI 命令提供统一的数据库记录接口

    特性：
    - 支持嵌套调用（scheduler 调用 check/manifests 时不会重复记录）
    - 自动检测和复用现有的 scan
    """

    def __init__(self):
        self.db = get_database()
        self.current_scan_id: Optional[int] = None
        self.current_manifest_id: Optional[int] = None
        self._scan_depth: int = 0  # scan 嵌套深度
        self._scan_finished: bool = False  # 标记 scan 是否已完成

    # 扫描记录
    def start_scan(
        self,
        command: str,
        trigger_source: str = "cli"
    ) -> ScanRecord:
        """
        开始扫描记录（支持嵌套）

        :param command: 命令名称 (check/manifests/pr/scheduler)
        :param trigger_source: 触发源 (cli/api/scheduler)
        :return: ScanRecord 对象

        嵌套调用处理：
        - 如果已有活动的 scan，增加深度计数，返回现有 scan
        - 如果没有，创建新的 scan
        """
        self._scan_depth += 1

        if self.current_scan_id is not None:
            # 已有活动的 scan，复用它（避免重复记录）
            logger.debug(f"[DB] Reusing existing scan {self.current_scan_id} for nested command: {command} (depth: {self._scan_depth})")
            return self.db.get_scan_by_id(self.current_scan_id)

        # 没有活动的 scan，创建新的
        # 根据 trigger_source 确定 scan_type
        scan_type = "scheduled" if trigger_source == "scheduler" else "manual"

        # 只在创建新 scan 时重置完成标志
        self._scan_finished = False

        scan = self.db.create_scan_record(
            scan_type=scan_type,
            trigger_source=trigger_source,
            status="running"
        )
        self.current_scan_id = scan.id
        logger.info(f"[DB] Started scan {scan.id} (type={scan_type}) for command: {command} (depth: {self._scan_depth})")
        return scan

    def finish_scan(
        self,
        status: str,
        total_packages: int = 0,
        updated_packages: int = 0,
        success_packages: int = 0,
        failed_packages: int = 0
    ) -> Optional[ScanRecord]:
        """
        完成扫描记录（支持嵌套）

        :param status: 最终状态
        :param total_packages: 总包数
        :param updated_packages: 有更新的包数
        :param success_packages: 成功处理的包数
        :param failed_packages: 失败的包数
        :return: 更新后的 ScanRecord（如果是嵌�调用，返回 None）

        嵌套调用处理：
        - 只有在顶层 scan（depth=1）时才真正完成并关闭 scan
        - 嵌套调用只减少深度计数
        - 如果已经完成过，跳过（避免重复完成）
        """
        self._scan_depth -= 1

        if self._scan_depth > 0:
            # 嵌套调用，不真正完成 scan
            logger.debug(f"[DB] Nested finish_scan called (depth: {self._scan_depth}), skipping actual finish")
            return None

        # 检查是否已经完成过（避免重复调用）
        if self._scan_finished:
            logger.debug(f"[DB] Scan already finished, skipping duplicate finish_scan call")
            return None

        if not self.current_scan_id:
            logger.warning("[DB] No active scan to finish")
            return None

        scan = self.db.update_scan_record(
            self.current_scan_id,
            status=status,
            end_time=datetime.now(),
            total_packages=total_packages,
            updated_packages=updated_packages,
            success_packages=success_packages,
            failed_packages=failed_packages
        )

        logger.info(f"[DB] Finished scan {scan.id}: {status} (total={total_packages}, updated={updated_packages})")
        self._scan_finished = True  # 标记为已完成
        self.current_scan_id = None  # 清除 scan ID
        return scan

    # 版本检查记录
    def record_version_check(
        self,
        package_name: str,
        new_version: str,
        old_version: Optional[str] = None,
        check_status: str = "updated",
        nvchecker_event: Optional[str] = None,
        nvchecker_url: Optional[str] = None
    ) -> PackageUpdate:
        """
        记录版本检查结果

        :param package_name: 包名
        :param new_version: 新版本
        :param old_version: 旧版本
        :param check_status: 检查状态
        :param nvchecker_event: nvchecker 事件类型
        :param nvchecker_url: 版本发布 URL
        :return: PackageUpdate 对象
        """
        if not self.current_scan_id:
            # 如果没有活动扫描，自动创建一个
            self.start_scan(command="check")

        pkg_update = self.db.create_package_update(
            scan_id=self.current_scan_id,
            package_name=package_name,
            old_version=old_version,
            new_version=new_version,
            check_status=check_status,
            nvchecker_event=nvchecker_event,
            nvchecker_url=nvchecker_url
        )

        logger.info(f"[DB] Recorded version check: {package_name} {old_version} → {new_version}")
        return pkg_update

    # Manifest 生成记录
    def record_manifest_generation(
        self,
        package_name: str,
        combo_name: str,
        version: str,
        status: str,  # 'success' / 'failed' / 'skipped'
        # 成功时的字段
        manifest_path: Optional[str] = None,
        manifest_size: Optional[int] = None,
        manifest_hash: Optional[str] = None,
        # 失败时的字段
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        error_code: Optional[int] = None,
        error_details: Optional[str] = None,
        # 跳过时的字段
        skip_reason: Optional[str] = None
    ) -> ManifestRecord:
        """
        记录 Manifest 生成结果（简化版 v2）

        :param package_name: 包名
        :param combo_name: combo 名称
        :param version: 版本
        :param status: 生成状态 - 'success' / 'failed' / 'skipped'
        :param manifest_path: manifest 文件路径（成功时）
        :param manifest_size: 文件大小（成功时）
        :param manifest_hash: 文件哈希（成功时）
        :param error_type: 错误类型（失败时）
        :param error_message: 错误消息（失败时）
        :param error_code: HTTP 状态码等（失败时）
        :param error_details: 错误详情 JSON（失败时）
        :param skip_reason: 跳过原因（跳过时）
        :return: ManifestRecord 对象
        """
        if not self.current_scan_id:
            # 如果没有活动扫描，自动创建一个
            self.start_scan(command="manifests")

        manifest = self.db.create_manifest_record(
            scan_id=self.current_scan_id,
            package_name=package_name,
            combo_name=combo_name,
            version=version,
            status=status,
            manifest_path=manifest_path,
            manifest_size=manifest_size,
            manifest_hash=manifest_hash,
            error_type=error_type,
            error_message=error_message,
            error_code=error_code,
            error_details=error_details,
            skip_reason=skip_reason
        )

        logger.info(f"[DB] Recorded manifest generation: {package_name}/{combo_name} - {status}")
        return manifest

    # PR 创建记录
    def record_pr_creation(
        self,
        package_name: str,
        version: str,
        status: str,  # 'success' / 'failed' / 'skipped'
        manifest_id: Optional[int] = None,
        # 成功时的字段
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        # 失败时的字段
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        error_details: Optional[str] = None,
        # 跳过时的字段
        skip_reason: Optional[str] = None
    ) -> PRRecord:
        """
        记录 PR 创建结果

        :param package_name: 包名
        :param version: 版本
        :param status: 创建状态 - 'success' / 'failed' / 'skipped'
        :param manifest_id: manifest 记录 ID
        :param pr_number: PR 编号（成功时）
        :param pr_url: PR URL（成功时）
        :param branch_name: 分支名称（成功时）
        :param repo_owner: 仓库所有者（成功时）
        :param repo_name: 仓库名称（成功时）
        :param error_type: 错误类型（失败时）
        :param error_message: 错误消息（失败时）
        :param error_details: 错误详情 JSON（失败时）
        :param skip_reason: 跳过原因（跳过时）
        :return: PRRecord 对象
        """
        if not self.current_scan_id:
            # 如果没有活动扫描，自动创建一个
            self.start_scan(command="pr")

        pr = self.db.create_pr_record(
            scan_id=self.current_scan_id,
            package_name=package_name,
            version=version,
            status=status,
            manifest_id=manifest_id,
            pr_number=pr_number,
            pr_url=pr_url,
            branch_name=branch_name,
            repo_owner=repo_owner,
            repo_name=repo_name,
            error_type=error_type,
            error_message=error_message,
            error_details=error_details,
            skip_reason=skip_reason
        )

        logger.info(f"[DB] Recorded PR creation: {package_name} - {status}")
        if pr_number:
            logger.info(f"[DB]   PR #{pr_number}: {pr_url}")

        return pr

    # 通用失败记录方法
    def record_error(
        self,
        package_name: str,
        error: Exception,
        failure_step: Optional[str] = None,
        version: Optional[str] = None,
        include_traceback: bool = True
    ) -> ManifestRecord:
        """
        记录错误到 manifest_records 表

        :param package_name: 包名
        :param error: 异常对象
        :param failure_step: 具体失败步骤
        :param version: 版本
        :param include_traceback: 是否包含堆栈跟踪
        :return: ManifestRecord 对象
        """
        if not self.current_scan_id:
            # 如果没有活动扫描，自动创建一个
            self.start_scan(command="unknown")

        # 提取错误信息
        error_type = type(error).__name__
        error_message = str(error)
        error_code = getattr(error, 'code', None) or getattr(error, 'status', None)

        # 构建错误详情
        error_details_dict: Dict[str, Any] = {
            "error_type": error_type,
            "error_message": error_message
        }

        # 添加 HTTP 状态码（如果有）
        if error_code:
            error_details_dict["error_code"] = error_code

        # 添加堆栈跟踪
        if include_traceback:
            error_details_dict["traceback"] = format_exception(type(error), error, error.__traceback__)

        # 转换为 JSON 字符串
        import json
        error_details_json = json.dumps(error_details_dict)

        # 创建 manifest 失败记录
        manifest = self.db.create_manifest_record(
            scan_id=self.current_scan_id,
            package_name=package_name,
            combo_name="",  # 错误记录时 combo 可以为空
            version=version or "unknown",
            status="failed",
            error_type=error_type,
            error_message=error_message,
            error_code=error_code,
            error_details=error_details_json
        )

        logger.error(f"[DB] Recorded error: {package_name} - {error_type}: {error_message}")
        return manifest


# 全局记录器实例
_global_recorder: Optional[CommandRecorder] = None


def get_recorder() -> CommandRecorder:
    """获取全局记录器实例"""
    global _global_recorder
    if _global_recorder is None:
        _global_recorder = CommandRecorder()
    return _global_recorder


# 装饰器：自动记录命令执行
def record_command(command_name: str):
    """
    装饰器：自动记录命令执行

    使用方式：
    @record_command("check")
    def check():
        # ... 命令逻辑 ...
        pass

    装饰器功能：
    自动调用 start_scan() 开始扫描
    捕获异常并调用 finish_scan(status="failed")
    不记录具体的错误信息（由服务层自己记录）
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            recorder = get_recorder()

            # 开始记录（从上下文获取触发源）
            scan = recorder.start_scan(command=command_name, trigger_source=get_trigger_source())

            try:
                # 执行命令
                result = func(*args, **kwargs)

                # 完成记录
                recorder.finish_scan(status="completed")

                return result

            except Exception as e:
                logger.error(f"[DB] Command {command_name} failed: {e}")

                # 完成记录（失败状态，捕获可能的异常）
                try:
                    recorder.finish_scan(
                        status="failed",
                        failed_packages=1
                    )
                except Exception as db_err:
                    logger.error(f"[DB] Failed to finish scan: {db_err}")

                raise  # 重新抛出异常
        return wrapper
    return decorator
