import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from db.models import UserProfile

logger = logging.getLogger(__name__)


async def notify_child(bot: Bot, profile: UserProfile, message_text: str) -> bool:
    if not profile.child_telegram_id:
        return False
    name = profile.name or "родного человека"
    alert = f"Наум заметил тревожное сообщение от {name}: ‘{message_text[:500]}’. Лучше связаться с ней/ним сейчас."
    try:
        await bot.send_message(chat_id=profile.child_telegram_id, text=alert)
        return True
    except TelegramAPIError:
        logger.exception("Не удалось отправить тревожное уведомление родственнику %s", profile.child_telegram_id)
        return False
