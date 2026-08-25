import logging
from typing import List

from ...services.manifest_service import ManifestService

logger = logging.getLogger(__name__)


def manifests(up_name: str, gen_vers: List[str], down_grade: bool) -> None:
    ManifestService.generate(up_name, gen_vers, down_grade)
