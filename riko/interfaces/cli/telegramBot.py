import logging
from ...services.telegramBot_service import telegramBotService

logger = logging.getLogger(__name__)

def telegramBot() -> None:
    """
    启动 Telegram 机器人
    """
    # 启动 Bot
    telegramBotService()
