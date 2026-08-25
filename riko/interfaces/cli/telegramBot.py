import logging
from ...services.telegramBot_service import telegramBotService

logger = logging.getLogger(__name__)

def telegramBot() -> None:
    telegramBotService()
