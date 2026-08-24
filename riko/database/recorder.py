import logging
import functools
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from traceback import format_exception
from contextvars import ContextVar

from .db_manager import get_database
from .models import ScanRecord, PackageUpdate, ManifestRecord, PRRecord

logger = logging.getLogger(__name__)

# ContextVar keeps the trigger source thread-safe
_trigger_source_context: ContextVar[str] = ContextVar('trigger_source', default='cli')


def set_trigger_source(source: str) -> None:
    _trigger_source_context.set(source)


def get_trigger_source() -> str:
    return _trigger_source_context.get()


class CommandRecorder:

    def __init__(self):
        self.db = get_database()
        self.current_scan_id: Optional[int] = None
        self.current_manifest_id: Optional[int] = None
        self._scan_depth: int = 0  # scan nesting depth
        self._scan_finished: bool = False  # whether the scan is finished

    def start_scan(
        self,
        command: str,
        trigger_source: str = "cli"
    ) -> ScanRecord:
        self._scan_depth += 1

        if self.current_scan_id is not None:
            # Reuse the active scan for nested commands
            logger.debug(f"[DB] Reusing existing scan {self.current_scan_id} for nested command: {command} (depth: {self._scan_depth})")
            return self.db.get_scan_by_id(self.current_scan_id)

        # Create a new scan
        scan_type = "scheduled" if trigger_source == "scheduler" else "manual"

        # Reset the finished flag only for a new scan
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
        self._scan_depth -= 1

        if self._scan_depth > 0:
            # Nested call: do not actually finish
            logger.debug(f"[DB] Nested finish_scan called (depth: {self._scan_depth}), skipping actual finish")
            return None

        # Avoid duplicate finish calls
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
        self._scan_finished = True
        self.current_scan_id = None
        return scan

    def record_version_check(
        self,
        package_name: str,
        new_version: str,
        old_version: Optional[str] = None,
        check_status: str = "updated",
        nvchecker_event: Optional[str] = None,
        nvchecker_url: Optional[str] = None
    ) -> PackageUpdate:
        if not self.current_scan_id:
            # Auto-create a scan if none is active
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

    def record_manifest_generation(
        self,
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
        if not self.current_scan_id:
            # Auto-create a scan if none is active
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

    def record_pr_creation(
        self,
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
        if not self.current_scan_id:
            # Auto-create a scan if none is active
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

    def record_error(
        self,
        package_name: str,
        error: Exception,
        failure_step: Optional[str] = None,
        version: Optional[str] = None,
        include_traceback: bool = True
    ) -> ManifestRecord:
        if not self.current_scan_id:
            # Auto-create a scan if none is active
            self.start_scan(command="unknown")

        error_type = type(error).__name__
        error_message = str(error)
        error_code = getattr(error, 'code', None) or getattr(error, 'status', None)

        error_details_dict: Dict[str, Any] = {
            "error_type": error_type,
            "error_message": error_message
        }

        # Add HTTP status code if present
        if error_code:
            error_details_dict["error_code"] = error_code

        # Add traceback
        if include_traceback:
            error_details_dict["traceback"] = format_exception(type(error), error, error.__traceback__)

        # Serialize to JSON
        import json
        error_details_json = json.dumps(error_details_dict)

        # Record the failure
        manifest = self.db.create_manifest_record(
            scan_id=self.current_scan_id,
            package_name=package_name,
            combo_name="",  # combo may be empty for errors
            version=version or "unknown",
            status="failed",
            error_type=error_type,
            error_message=error_message,
            error_code=error_code,
            error_details=error_details_json
        )

        logger.error(f"[DB] Recorded error: {package_name} - {error_type}: {error_message}")
        return manifest


_global_recorder: Optional[CommandRecorder] = None


def get_recorder() -> CommandRecorder:
    global _global_recorder
    if _global_recorder is None:
        _global_recorder = CommandRecorder()
    return _global_recorder


def record_command(command_name: str):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            recorder = get_recorder()

            # Start recording using the context trigger source
            scan = recorder.start_scan(command=command_name, trigger_source=get_trigger_source())

            try:
                result = func(*args, **kwargs)

                recorder.finish_scan(status="completed")

                return result

            except Exception as e:
                logger.error(f"[DB] Command {command_name} failed: {e}")

                # Finish with failed status
                try:
                    recorder.finish_scan(
                        status="failed",
                        failed_packages=1
                    )
                except Exception as db_err:
                    logger.error(f"[DB] Failed to finish scan: {db_err}")

                raise
        return wrapper
    return decorator
