#!/usr/bin/env python3
# riko/database/db_manager.py - 数据库管理器
"""
提供数据库初始化、会话管理和常用查询方法

类似于 Java 的 Spring Data JPA Repository 模式
"""

import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Type, TypeVar
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select, func, and_, or_
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from .models import Base, ScanRecord, PackageUpdate, ManifestRecord, PRRecord

logger = logging.getLogger(__name__)

# 泛型类型变量
T = TypeVar('T', bound=Base)


# ========== 数据库管理器 ==========
class DatabaseManager:
    """
    数据库管理器

    职责：
    1. 数据库初始化和连接管理
    2. 提供会话管理（上下文管理器）
    3. 提供常用的数据库操作方法

    使用方式类似于 Java 的 EntityManager 或 DbContext
    """

    def __init__(self, db_path: str | Path):
        """
        初始化数据库管理器

        :param db_path: 数据库文件路径（SQLite）
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建数据库引擎
        # SQLite 连接字符串: sqlite:///path/to/database.db
        database_url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(
            database_url,
            echo=False,  # 关闭 SQL 语句输出（避免日志过多）
            connect_args={"check_same_thread": False},  # SQLite 特定配置
        )

        # 创建会话工厂
        # 每个线程都有自己的会话（线程安全）
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        logger.info(f"Database initialized: {self.db_path}")

    def create_tables(self) -> None:
        """创建所有表（如果不存在）"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except SQLAlchemyError as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    def drop_tables(self) -> None:
        """删除所有表（谨慎使用！）"""
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.warning("All database tables dropped")
        except SQLAlchemyError as e:
            logger.error(f"Failed to drop tables: {e}")
            raise

    @contextmanager
    def get_session(self):
        """
        获取数据库会话（上下文管理器）

        使用方式：
        with db_manager.get_session() as session:
            session.query(...)

        类似于 Java 的 try-with-resources
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    # ========== 扫描记录相关方法 ==========

    def get_scan_by_id(self, scan_id: int) -> ScanRecord:
        """
        根据 ID 获取扫描记录

        :param scan_id: 扫描记录 ID
        :return: ScanRecord 对象
        """
        with self.get_session() as session:
            record = session.query(ScanRecord).filter(ScanRecord.id == scan_id).first()
            if record:
                session.expunge(record)
            return record

    def create_scan_record(
        self,
        scan_type: str,
        trigger_source: Optional[str] = None,
        status: str = "running"
    ) -> ScanRecord:
        """
        创建新的扫描记录

        :param scan_type: 扫描类型 ('manual' / 'scheduled')
        :param trigger_source: 触发源 ('scheduler' / 'cli' / 'api')
        :param status: 初始状态
        :return: 创建的 ScanRecord 对象
        """
        with self.get_session() as session:
            record = ScanRecord(
                scan_type=scan_type,
                trigger_source=trigger_source,
                status=status,
                start_time=datetime.now()
            )
            session.add(record)
            session.flush()  # 获取 ID
            session.expunge(record)  # 将对象从 session 中分离
            return record
        # 上下文管理器退出时会自动提交

    def update_scan_record(
        self,
        scan_id: int,
        **kwargs
    ) -> Optional[ScanRecord]:
        """
        更新扫描记录

        :param scan_id: 扫描记录 ID
        :param kwargs: 要更新的字段
        :return: 更新后的 ScanRecord 对象
        """
        with self.get_session() as session:
            record = session.get(ScanRecord, scan_id)
            if record:
                for key, value in kwargs.items():
                    if hasattr(record, key):
                        setattr(record, key, value)
                session.flush()
                session.expunge(record)
                return record
            return None

    def get_recent_scans(
        self,
        limit: int = 10,
        status: Optional[str] = None
    ) -> List[ScanRecord]:
        """
        获取最近的扫描记录

        :param limit: 返回数量限制
        :param status: 过滤状态（可选）
        :return: ScanRecord 列表
        """
        with self.get_session() as session:
            query = session.query(ScanRecord)
            if status:
                query = query.filter(ScanRecord.status == status)
            results = query.order_by(ScanRecord.scan_time.desc()).limit(limit).all()
            # 将所有对象从 session 中分离
            for obj in results:
                session.expunge(obj)
            return results

    # ========== 包更新记录相关方法 ==========

    def create_package_update(
        self,
        scan_id: int,
        package_name: str,
        new_version: str,
        old_version: Optional[str] = None,
        check_status: str = "updated",
        nvchecker_event: Optional[str] = None,
        nvchecker_url: Optional[str] = None
    ) -> PackageUpdate:
        """创建包更新记录"""
        with self.get_session() as session:
            record = PackageUpdate(
                scan_id=scan_id,
                package_name=package_name,
                old_version=old_version,
                new_version=new_version,
                check_status=check_status,
                nvchecker_event=nvchecker_event,
                nvchecker_url=nvchecker_url
            )
            session.add(record)
            session.flush()
            session.expunge(record)
            return record

    def get_updates_by_scan(self, scan_id: int) -> List[PackageUpdate]:
        """获取某个扫描的所有更新记录"""
        with self.get_session() as session:
            results = session.query(PackageUpdate).filter(
                PackageUpdate.scan_id == scan_id
            ).all()
            for obj in results:
                session.expunge(obj)
            return results

    # ========== Manifest 记录相关方法 ==========

    def create_manifest_record(
        self,
        scan_id: int,
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
        创建 Manifest 生成记录（简化版 v2）

        :param scan_id: 扫描记录 ID
        :param package_name: 包名
        :param combo_name: Combo 名称
        :param version: 版本
        :param status: 生成状态 - 'success' / 'failed' / 'skipped'
        :param manifest_path: Manifest 文件路径（成功时）
        :param manifest_size: 文件大小（成功时）
        :param manifest_hash: 文件哈希（成功时）
        :param error_type: 错误类型（失败时）
        :param error_message: 错误消息（失败时）
        :param error_code: HTTP 状态码等（失败时）
        :param error_details: 错误详情 JSON（失败时）
        :param skip_reason: 跳过原因（跳过时）
        :return: 创建的 ManifestRecord 对象
        """
        with self.get_session() as session:
            record = ManifestRecord(
                scan_id=scan_id,
                package_name=package_name,
                combo_name=combo_name,
                version=version,
                status=status,  # 统一的状态字段
                # 成功时的字段
                manifest_path=manifest_path,
                manifest_size=manifest_size,
                manifest_hash=manifest_hash,
                # 失败时的字段
                error_type=error_type,
                error_message=error_message,
                error_code=error_code,
                error_details=error_details,
                # 跳过时的字段
                skip_reason=skip_reason
            )
            session.add(record)
            session.flush()
            session.expunge(record)
            return record

    def update_manifest_record(
        self,
        manifest_id: int,
        **kwargs
    ) -> Optional[ManifestRecord]:
        """
        更新 Manifest 记录

        :param manifest_id: Manifest 记录 ID
        :param kwargs: 要更新的字段（status, manifest_path, error_type 等）
        :return: 更新后的 ManifestRecord 对象
        """
        with self.get_session() as session:
            record = session.get(ManifestRecord, manifest_id)
            if record:
                for key, value in kwargs.items():
                    if hasattr(record, key):
                        setattr(record, key, value)
                session.flush()
                session.expunge(record)
                return record
            return None

    # ========== PR 记录相关方法 ==========

    def create_pr_record(
        self,
        scan_id: int,
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
        创建 PR 记录（简化版 v2）

        :param scan_id: 扫描记录 ID
        :param package_name: 包名
        :param version: 版本
        :param status: 创建状态 - 'success' / 'failed' / 'skipped'
        :param manifest_id: manifest 记录 ID（可选）
        :param pr_number: PR 编号（成功时）
        :param pr_url: PR URL（成功时）
        :param branch_name: 功能分支名（成功时）
        :param repo_owner: 仓库所有者（成功时）
        :param repo_name: 仓库名称（成功时）
        :param error_type: 错误类型（失败时）
        :param error_message: 错误消息（失败时）
        :param error_details: 错误详情 JSON（失败时）
        :param skip_reason: 跳过原因（跳过时）
        :return: 创建的 PRRecord 对象
        """
        with self.get_session() as session:
            record = PRRecord(
                scan_id=scan_id,
                manifest_id=manifest_id,
                package_name=package_name,
                version=version,
                status=status,  # 统一的状态字段
                # 成功时的字段
                repo_owner=repo_owner,
                repo_name=repo_name,
                pr_number=pr_number,
                pr_url=pr_url,
                branch_name=branch_name,
                # 失败时的字段
                error_type=error_type,
                error_message=error_message,
                error_details=error_details,
                # 跳过时的字段
                skip_reason=skip_reason
            )
            session.add(record)
            session.flush()
            session.expunge(record)
            return record

    # ========== 通用查询方法 ==========

    def get_by_id(self, model: Type[T], record_id: int) -> Optional[T]:
        """
        根据 ID 获取记录
        注意：此方法会预加载所有关系并分离对象
        """
        with self.get_session() as session:
            result = session.get(model, record_id)
            if result:
                # 预加载所有关系（使用 eager loading）
                from sqlalchemy.orm import selectinload
                if hasattr(result, 'package_updates'):
                    session.query(type(result)).options(
                        selectinload(type(result).package_updates)
                    ).get(record_id)
                    # 重新获取以加载关系
                    result = session.get(model, record_id)
                session.expunge(result)
            return result

    def count_records(self, model: Type[T]) -> int:
        """统计某个模型的记录数"""
        with self.get_session() as session:
            return session.query(func.count(model.id)).scalar()


# ========== 全局数据库实例 ==========
def get_database(db_path: Optional[str | Path] = None) -> DatabaseManager:
    """
    获取数据库管理器实例

    :param db_path: 数据库路径（可选，默认使用配置中的路径）
    :return: DatabaseManager 实例
    """
    from ..config.const import basedir

    if db_path is None:
        # 默认数据库路径
        db_path = basedir / "cache" / "riko" / "riko_history.db"

    return DatabaseManager(db_path)
