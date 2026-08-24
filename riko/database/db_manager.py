import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Type, TypeVar
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select, func, and_, or_
from sqlalchemy.orm import Session, sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from .models import Base, ScanRecord, PackageUpdate, ManifestRecord, PRRecord
from ..config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=Base)


class DatabaseManager:

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Use the configured URL or default to the sqlite path
        database_url = settings.database_url or f"sqlite:///{self.db_path}"

        # SQLite requires check_same_thread=False
        connect_args = {
            "check_same_thread": False,
        }
        if database_url.startswith("sqlite:///"):
            # Add SQLite timeout/isolation options
            database_url = f"{database_url}?timeout=20&isolation_level=None"

        self.engine = create_engine(
            database_url,
            echo=settings.database_echo,
            connect_args=connect_args,
            poolclass=StaticPool,  # SQLite uses a static connection pool
            pool_pre_ping=True,
        )

        # scoped_session gives each thread its own session
        self.SessionLocal = scoped_session(
            sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
        )

        logger.info(f"Database initialized: {self.db_path}")

    def create_tables(self) -> None:
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except SQLAlchemyError as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    def drop_tables(self) -> None:
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.warning("All database tables dropped")
        except SQLAlchemyError as e:
            logger.error(f"Failed to drop tables: {e}")
            raise

    @contextmanager
    def get_session(self):
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            # close() returns the session to the pool instead of closing the connection
            session.close()

    def get_scan_by_id(self, scan_id: int) -> ScanRecord:
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
        with self.get_session() as session:
            record = ScanRecord(
                scan_type=scan_type,
                trigger_source=trigger_source,
                status=status,
                start_time=datetime.now()
            )
            session.add(record)
            session.flush()  # get the generated ID
            session.expunge(record)  # detach from session
            return record
        # The context manager commits on exit

    def update_scan_record(
        self,
        scan_id: int,
        **kwargs
    ) -> Optional[ScanRecord]:
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
        with self.get_session() as session:
            query = session.query(ScanRecord)
            if status:
                query = query.filter(ScanRecord.status == status)
            results = query.order_by(ScanRecord.scan_time.desc()).limit(limit).all()
            # detach objects from session
            for obj in results:
                session.expunge(obj)
            return results

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
        with self.get_session() as session:
            results = session.query(PackageUpdate).filter(
                PackageUpdate.scan_id == scan_id
            ).all()
            for obj in results:
                session.expunge(obj)
            return results

    def create_manifest_record(
        self,
        scan_id: int,
        package_name: str,
        combo_name: str,
        version: str,
        status: str,  # 'success' / 'failed' / 'skipped'
        # success fields
        manifest_path: Optional[str] = None,
        manifest_size: Optional[int] = None,
        manifest_hash: Optional[str] = None,
        # failure fields
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        error_code: Optional[int] = None,
        error_details: Optional[str] = None,
        # skip fields
        skip_reason: Optional[str] = None
    ) -> ManifestRecord:
        with self.get_session() as session:
            record = ManifestRecord(
                scan_id=scan_id,
                package_name=package_name,
                combo_name=combo_name,
                version=version,
                status=status,  # unified status field
                # success fields
                manifest_path=manifest_path,
                manifest_size=manifest_size,
                manifest_hash=manifest_hash,
                # failure fields
                error_type=error_type,
                error_message=error_message,
                error_code=error_code,
                error_details=error_details,
                # skip fields
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

    def create_pr_record(
        self,
        scan_id: int,
        package_name: str,
        version: str,
        status: str,  # 'success' / 'failed' / 'skipped'
        manifest_id: Optional[int] = None,
        # success fields
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        # failure fields
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        error_details: Optional[str] = None,
        # skip fields
        skip_reason: Optional[str] = None
    ) -> PRRecord:
        with self.get_session() as session:
            record = PRRecord(
                scan_id=scan_id,
                manifest_id=manifest_id,
                package_name=package_name,
                version=version,
                status=status,  # unified status field
                # success fields
                repo_owner=repo_owner,
                repo_name=repo_name,
                pr_number=pr_number,
                pr_url=pr_url,
                branch_name=branch_name,
                # failure fields
                error_type=error_type,
                error_message=error_message,
                error_details=error_details,
                # skip fields
                skip_reason=skip_reason
            )
            session.add(record)
            session.flush()
            session.expunge(record)
            return record

    def get_by_id(self, model: Type[T], record_id: int) -> Optional[T]:
        from sqlalchemy.orm import selectinload

        with self.get_session() as session:
            query = session.query(model)

            # Eager-load relationships depending on the model type
            if model == ScanRecord:
                query = query.options(
                    selectinload(ScanRecord.package_updates),
                    selectinload(ScanRecord.manifest_records),
                    selectinload(ScanRecord.pr_records)
                )
            elif model == ManifestRecord:
                query = query.options(selectinload(ManifestRecord.scan_record))
            elif model == PRRecord:
                query = query.options(selectinload(PRRecord.scan_record))
            elif model == PackageUpdate:
                query = query.options(selectinload(PackageUpdate.scan_record))

            result = query.filter(model.id == record_id).first()

            if result:
                session.expunge(result)
            return result

    def count_records(self, model: Type[T]) -> int:
        with self.get_session() as session:
            return session.query(func.count(model.id)).scalar()


def get_database(db_path: Optional[str | Path] = None) -> DatabaseManager:
    from ..config.const import basedir

    if db_path is None:
        db_path = basedir / "cache" / "riko" / "riko_history.db"

    db = DatabaseManager(db_path)
    db.create_tables()
    return db
