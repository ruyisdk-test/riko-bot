#!/usr/bin/env python3

import argparse
import logging
import sys
from datetime import datetime

from ...config.const import dry_run_docs_dir
from ...services.version_sync_service import VersionSyncService

logger = logging.getLogger(__name__)


def version_sync(args: argparse.Namespace) -> None:
    if getattr(args, 'dry_run', False):
        # share the same dir and timestamp so .log and .md pair up
        args.dry_run_report_dir = dry_run_docs_dir
        args.dry_run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dry_run_docs_dir.mkdir(parents=True, exist_ok=True)

        log_file = dry_run_docs_dir / f"version-sync-{args.dry_run_timestamp}.log"

        root_logger = logging.getLogger()
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root_logger.addHandler(file_handler)

        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.INFO)
        stdout_handler.setFormatter(logging.Formatter('%(message)s'))
        root_logger.addHandler(stdout_handler)

        logger.info(f"Dry-run logs will be saved to: {log_file}")

    VersionSyncService.sync_all(args)
