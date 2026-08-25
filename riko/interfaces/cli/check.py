import logging

from ...services.check_service import CheckService

logger = logging.getLogger(__name__)


def check() -> None:
    CheckService.run()
