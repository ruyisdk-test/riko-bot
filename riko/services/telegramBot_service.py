import logging
import os
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.error import TelegramError
from telegram.request import HTTPXRequest
import httpx

from ..config.settings import settings

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


_bot_instance: Bot = None

def get_proxy_config():
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')

    if http_proxy:
        logger.info(f"Using HTTP proxy: {http_proxy}")
        return http_proxy
    else:
        logger.info("No proxy configured, connecting directly")
        return None

def get_bot() -> Bot:
    global _bot_instance

    if _bot_instance is None:
        if not settings.telegram_token:
            raise ValueError("TELEGRAM_TOKEN is not configured")

        proxy_url = get_proxy_config()

        if proxy_url:
            request = HTTPXRequest(
                connect_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0,
                pool_timeout=30.0,
                proxy=httpx.Proxy(proxy_url)
            )
            logger.info(f"Created Bot instance (with proxy: {proxy_url})")
        else:
            request = HTTPXRequest(
                connect_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0,
                pool_timeout=30.0
            )
            logger.info("Created Bot instance (no proxy)")

        _bot_instance = Bot(token=settings.telegram_token, request=request)

    return _bot_instance

async def send_message(message: str, chat_id: int = None) -> bool:
    if not settings.telegram_token:
        logger.warning("[Telegram] TELEGRAM_TOKEN not configured, skipping send")
        return False

    target_chat_id = chat_id or getattr(settings, 'telegram_chat_id', None)
    if not target_chat_id:
        logger.warning("[Telegram] CHAT_ID not configured, skipping send")
        return False

    try:
        if isinstance(target_chat_id, str):
            target_chat_id = int(target_chat_id)
    except (ValueError, TypeError):
        logger.error(f"[Telegram] Invalid chat ID: {target_chat_id}")
        return False

    try:
        bot = get_bot()

        await bot.send_message(
            chat_id=target_chat_id,
            text=message,
            parse_mode='Markdown'
        )

        logger.info(f"[Telegram] Message sent to {target_chat_id}")
        return True

    except TelegramError as e:
        logger.error(f"[Telegram] API error: {e}")
        return False

    except Exception as e:
        logger.error(f"[Telegram] Failed to send message: {e}")
        return False


async def notify_scan_summary(
    total_packages: int,
    updated_packages: int,
    success_packages: int,
    failed_packages: int,
    updated_list: list = None,
    failed_list: list = None,
) -> bool:
    if updated_packages == 0 and failed_packages == 0:
        logger.info("[Telegram] No updates or failures, skipping notification")
        return False

    status_emoji = "access" if failed_packages == 0 else "warning"

    message = f"""{status_emoji} *Ruyi package update check completed*

*📊 Statistics*
• Total packages: {total_packages}
• Updated packages: {updated_packages}
• Success: {success_packages}
• Failed: {failed_packages}"""

    if updated_packages > 0 and updated_list:
        message += "\n\n*📦 Updated packages*:\n"
        for pkg in updated_list[:10]:  # show at most 10
            name = pkg.get("name", "unknown")
            old = pkg.get("old_version", "?")
            new = pkg.get("new_version", "?")
            message += f"  • `{name}`: {old} → {new}\n"

        if len(updated_list) > 10:
            message += f"  _... and {len(updated_list) - 10} more packages_\n"

    if failed_packages > 0:
        message += f"\n* Failed packages*: {failed_packages}\n"
        if failed_list:
            for pkg in failed_list[:10]:  # show at most 10
                name = pkg.get("name", "unknown")
                message += f"  • `{name}`\n"

            if len(failed_list) > 10:
                message += f"  _... and {len(failed_list) - 10} more packages_\n"

    return await send_message(message.strip())



async def echo(update: Update, context) -> None:
    await update.message.reply_text(update.message.text)


async def start(update: Update, context) -> None:
    await update.message.reply_text(
        'Welcome to Riko Bot!\n\n'
        'This is a Telegram bot for Ruyi Packaging Bot.\n'
        'Send any message and I will echo it back.'
    )


async def error(update: Update, context) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def telegramBotService():
    builder = ApplicationBuilder().token(settings.telegram_token)

    proxy_config = get_proxy_config()
    if proxy_config is not None:
        if isinstance(proxy_config, str):
            builder = builder.proxy(proxy_config)
            logger.info(f"Configured proxy: {proxy_config}")

    try:
        builder = builder.connect_timeout(30.0).pool_timeout(30.0)
    except Exception as e:
        logger.warning(f"Failed to configure timeouts: {e}")

    application = builder.build()

    application.add_handler(CommandHandler("start", start))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    application.add_error_handler(error)

    logger.info("Starting Telegram Bot...")
    logger.info("If connection fails, check:")
    logger.info("1. Network connectivity")
    logger.info("2. Whether a proxy is needed (set HTTP_PROXY or HTTPS_PROXY)")
    logger.info("3. Whether the Telegram token is correct")

    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        logger.error("Hint: a proxy is required to access the Telegram API from some regions")
        raise