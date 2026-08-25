#!/usr/bin/env python3

import argparse
import logging

from ...services.pr_service import PRService

logger = logging.getLogger(__name__)


def pr(args: argparse.Namespace) -> None:
    PRService.create(args)
