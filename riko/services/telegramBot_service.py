"""
Telegram Bot Service - Telegram 机器人服务

本服务用于通过 Telegram Bot 接收和发送消息
兼容 python-telegram-bot v20+

使用 python-telegram-bot 标准方法，而不是直接调用 HTTP API
支持通过代理连接（适用于中国大陆用户）
"""

import logging
import os
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.error import TelegramError
from telegram.request import HTTPXRequest
import httpx

from ..config.settings import settings

# 启用日志记录
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# 全局 Bot 实例（用于程序化发送消息）
_bot_instance: Bot = None

# 获取代理配置
def get_proxy_config():
    """
    支持以下环境变量：
    - HTTP_PROXY / HTTPS_PROXY: HTTP 代理
    - NO_PROXY: 不使用代理的地址

    Returns:
        str: 代理 URL，如果没有配置则返回 None
    """
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')

    if http_proxy:
        logger.info(f"使用 HTTP 代理: {http_proxy}")
        return http_proxy
    else:
        logger.info("未配置代理，直接连接")
        return None

# 获取全局 Bot 实例（单例模式）
def get_bot() -> Bot:
    """
    使用 python-telegram-bot 的 Bot 类来发送消息，而不是手动调用 HTTP API

    Returns:
        Bot: Telegram Bot 实例

    Raises:
        ValueError: 如果未配置 TELEGRAM_TOKEN
    """
    global _bot_instance

    if _bot_instance is None:
        if not settings.telegram_token:
            raise ValueError("未配置 TELEGRAM_TOKEN")

        # 创建 Bot 实例，支持代理
        # 获取代理配置
        proxy_url = get_proxy_config()

        # 创建 HTTPXRequest 实例（支持代理）
        if proxy_url:
            # 使用代理创建 httpx 客户端
            request = HTTPXRequest(
                connect_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0,
                pool_timeout=30.0,
                proxy=httpx.Proxy(proxy_url)
            )
            logger.info(f"已创建 Bot 实例（使用代理: {proxy_url}）")
        else:
            request = HTTPXRequest(
                connect_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0,
                pool_timeout=30.0
            )
            logger.info("已创建 Bot 实例（无代理）")

        _bot_instance = Bot(token=settings.telegram_token, request=request)

    return _bot_instance

# 发送 Telegram 消息（用于程序化通知）
async def send_message(message: str, chat_id: int = None) -> bool:
    """
    使用 python-telegram-bot 的 Bot.send_message() 方法

    Args:
        message: 要发送的消息内容
        chat_id: 目标聊天 ID，如果不指定则使用配置中的默认值

    Returns:
        bool: 发送成功返回 True，失败返回 False
    """
    if not settings.telegram_token:
        logger.warning("[Telegram] 未配置 TELEGRAM_TOKEN，跳过发送")
        return False

    # 获取目标 chat_id
    target_chat_id = chat_id or getattr(settings, 'telegram_chat_id', None)
    if not target_chat_id:
        logger.warning("[Telegram] 未配置 CHAT_ID，跳过发送")
        return False

    # 确保 chat_id 是整数
    try:
        if isinstance(target_chat_id, str):
            target_chat_id = int(target_chat_id)
    except (ValueError, TypeError):
        logger.error(f"[Telegram] 无效的 Chat ID: {target_chat_id}")
        return False

    try:
        bot = get_bot()

        # 发送消息，使用 Markdown 格式
        await bot.send_message(
            chat_id=target_chat_id,
            text=message,
            parse_mode='Markdown'  # 使用 Markdown 格式化
        )

        logger.info(f"[Telegram] 消息已发送到 {target_chat_id}")
        return True

    except TelegramError as e:
        logger.error(f"[Telegram] API 错误: {e}")
        return False

    except Exception as e:
        logger.error(f"[Telegram] 发送消息失败: {e}")
        return False


async def notify_scan_summary(
    total_packages: int,
    updated_packages: int,
    success_packages: int,
    failed_packages: int,
    updated_list: list = None,
    failed_list: list = None,
) -> bool:
    """
    发送扫描结果摘要通知

    Args:
        total_packages: 总包数
        updated_packages: 更新的包数
        success_packages: 成功处理的包数
        failed_packages: 失败的包数
        updated_list: 更新的包列表，格式为 [{"name": "pkg", "old_version": "1.0", "new_version": "2.0"}, ...]

    Returns:
        bool: 发送成功返回 True，失败返回 False
    """
    # 如果没有更新且没有失败，不发送通知
    if updated_packages == 0 and failed_packages == 0:
        logger.info("[Telegram] 无更新且无失败，跳过通知")
        return False

    # 构建消息
    status_emoji = "✅" if failed_packages == 0 else "⚠️"

    message = f"""{status_emoji} *Ruyi 包更新检查完成*

*📊 统计信息*
• 总包数: {total_packages}
• 更新包数: {updated_packages}
• 成功: {success_packages}
• 失败: {failed_packages}"""

    # 添加更新详情
    if updated_packages > 0 and updated_list:
        message += "\n\n*📦 更新的包*:\n"
        for pkg in updated_list[:10]:  # 最多显示 10 个
            name = pkg.get("name", "unknown")
            old = pkg.get("old_version", "?")
            new = pkg.get("new_version", "?")
            message += f"  • `{name}`: {old} → {new}\n"

        if len(updated_list) > 10:
            message += f"  _... 还有 {len(updated_list) - 10} 个包_\n"

    # 添加失败提示
    if failed_packages > 0:
        message += f"\n* 失败的包*: {failed_packages}\n"
        if failed_list:
            for pkg in failed_list[:10]:  # 最多显示 10 个
                name = pkg.get("name", "unknown")
                message += f"  • `{name}`\n"

            if len(failed_list) > 10:
                message += f"  _... 还有 {len(failed_list) - 10} 个包_\n"

    return await send_message(message.strip())



# Telegram Bot 主程序（用于接收和处理用户消息）

async def echo(update: Update, context) -> None:
    """回显用户发送的消息"""
    await update.message.reply_text(update.message.text)


async def start(update: Update, context) -> None:
    """处理 /start 命令"""
    await update.message.reply_text(
        '欢迎使用 Riko Bot！\n\n'
        '这是一个用于 Ruyi Packaging Bot 的 Telegram 机器人。\n'
        '发送任何消息，我会回显给你。'
    )


async def error(update: Update, context) -> None:
    """记录错误"""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def telegramBotService():
    """
    启动 Telegram Bot

    使用 ApplicationBuilder 和 run_polling 来运行 Bot
    """
    # 创建 Application 构建器
    builder = ApplicationBuilder().token(settings.telegram_token)

    # 配置代理
    proxy_config = get_proxy_config()
    if proxy_config is not None:
        if isinstance(proxy_config, str):
            # HTTP 代理（字符串）
            # python-telegram-bot 会自动使用 httpx 的代理支持
            builder = builder.proxy(proxy_config)
            logger.info(f"已配置代理: {proxy_config}")

    # 添加连接池配置，增加超时时间
    try:
        builder = builder.connect_timeout(30.0).pool_timeout(30.0)
    except Exception as e:
        logger.warning(f"无法配置超时时间: {e}")

    # 构建 Application
    application = builder.build()

    # 添加命令处理程序
    application.add_handler(CommandHandler("start", start))

    # 添加消息处理程序（非命令文本消息
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # 添加错误处理程序
    application.add_error_handler(error)

    # 启动机器人
    logger.info("Starting Telegram Bot...")
    logger.info("如果连接失败，请检查：")
    logger.info("1. 网络连接是否正常")
    logger.info("2. 是否需要配置代理（设置 HTTP_PROXY 或 HTTPS_PROXY 环境变量）")
    logger.info("3. Telegram Token 是否正确")

    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Bot 启动失败: {e}")
        logger.error("提示: 在中国大陆，需要配置代理才能访问 Telegram API")
        raise