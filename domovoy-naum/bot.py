import asyncio
import logging
from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, Message

from config import get_settings
from db.database import Database
from services.alerts import notify_child
from services.openai_client import NaumOpenAIClient
from services.profiles import (
    PROFILE_FIELDS,
    add_message,
    format_profile,
    get_history,
    get_or_create_profile,
    reset_history,
    update_profile_field,
)
from services.safety import check_safety, needs_emotional_support, urgent_user_message
from services.speech import speech_to_text, text_to_speech
from services.vision import analyze_photo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

START_TEXT = (
    "Здравствуйте. Я Домовой Наум. Я могу помочь поговорить, разобраться с бытовым вопросом, "
    "подсказать по еде, растениям, здоровью без диагнозов и просто поддержать, если тревожно. "
    "Можно писать текстом, голосом или прислать фото."
)
HELP_TEXT = """Что я умею:
• отвечать на обычные вопросы текстом;
• понимать голосовые сообщения и отвечать текстом и голосом;
• смотреть фото еды, растений, цветов, насекомых, бытовых предметов и ошибок на экране;
• помогать с простыми блюдами, списком покупок, домом и огородом;
• мягко поддерживать, если тревожно или одиноко;
• подсказать безопасные бытовые шаги по здоровью, но без диагнозов и назначений.

Команды:
/start — знакомство
/profile — показать профиль
/set_profile — заполнить профиль
/reset — очистить историю разговора
/help — помощь
"""
FAIL_TEXT = "Сейчас не получилось обработать, попробуйте ещё раз чуть позже."
PROFILE_ORDER = list(PROFILE_FIELDS.keys())


class ProfileForm(StatesGroup):
    filling = State()


async def download_telegram_file(bot: Bot, file_id: str) -> bytes:
    tg_file = await bot.get_file(file_id)
    buffer = BytesIO()
    await bot.download_file(tg_file.file_path, destination=buffer)
    return buffer.getvalue()


def build_safety_note(text: str) -> str | None:
    safety = check_safety(text)
    if safety.emergency:
        return (
            "Пользователь написал потенциально опасный симптом или кризисную фразу. "
            "Ответь спокойно и коротко: посоветуй срочно вызвать 112/103, связаться с близкими, "
            "не вставать при слабости/падении. Не ставь диагноз и не назначай лекарства."
        )
    if needs_emotional_support(text):
        return (
            "Пользователю нужна эмоциональная поддержка. Признай чувство, не обесценивай, "
            "предложи одно маленькое действие: чай, дыхание, прогулку, звонок близкому или простую задачу."
        )
    return None


async def main() -> None:
    settings = get_settings()
    db = Database(settings)
    await db.init()

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    openai_client = NaumOpenAIClient(settings)

    @dp.message(Command("start"))
    async def start(message: Message) -> None:
        async with db.session() as session:
            await get_or_create_profile(session, message.from_user.id, settings.default_child_telegram_id)
        await message.answer(START_TEXT)

    @dp.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(HELP_TEXT)

    @dp.message(Command("profile"))
    async def profile_command(message: Message) -> None:
        async with db.session() as session:
            profile = await get_or_create_profile(session, message.from_user.id, settings.default_child_telegram_id)
            await message.answer(format_profile(profile))

    @dp.message(Command("reset"))
    async def reset_command(message: Message) -> None:
        async with db.session() as session:
            await get_or_create_profile(session, message.from_user.id, settings.default_child_telegram_id)
            await reset_history(session, message.from_user.id)
        await message.answer("Готово, я очистил историю нашего разговора. Профиль оставил на месте.")

    @dp.message(Command("set_profile"))
    async def set_profile_start(message: Message, state: FSMContext) -> None:
        async with db.session() as session:
            await get_or_create_profile(session, message.from_user.id, settings.default_child_telegram_id)
        await state.set_state(ProfileForm.filling)
        await state.update_data(field_index=0)
        field = PROFILE_ORDER[0]
        await message.answer(
            f"Давайте спокойно заполним профиль. Если что-то не хотите указывать — напишите ‘нет’ или ‘пропустить’.\n\n{PROFILE_FIELDS[field]}?"
        )

    @dp.message(ProfileForm.filling)
    async def set_profile_step(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        index = int(data.get("field_index", 0))
        field = PROFILE_ORDER[index]
        async with db.session() as session:
            profile = await get_or_create_profile(session, message.from_user.id, settings.default_child_telegram_id)
            await update_profile_field(session, profile, field, message.text or "")
        index += 1
        if index >= len(PROFILE_ORDER):
            await state.clear()
            async with db.session() as session:
                profile = await get_or_create_profile(session, message.from_user.id, settings.default_child_telegram_id)
                await message.answer("Спасибо, я запомнил.\n\n" + format_profile(profile))
            return
        await state.update_data(field_index=index)
        next_field = PROFILE_ORDER[index]
        await message.answer(f"{PROFILE_FIELDS[next_field]}?")

    @dp.message(F.voice)
    async def voice_message(message: Message) -> None:
        try:
            audio = await download_telegram_file(bot, message.voice.file_id)
            transcript = await speech_to_text(openai_client, audio, "voice.ogg")
            async with db.session() as session:
                profile = await get_or_create_profile(session, message.from_user.id, settings.default_child_telegram_id)
                history = await get_history(session, message.from_user.id)
                safety = check_safety(transcript)
                if safety.needs_alert:
                    await notify_child(bot, profile, transcript)
                note = build_safety_note(transcript)
                answer = await openai_client.text_answer(transcript, profile, history, note)
                await add_message(session, message.from_user.id, "user", transcript)
                await add_message(session, message.from_user.id, "assistant", answer)
            await message.answer(f"Я расслышал: {transcript}\n\n{answer}")
            try:
                voice_bytes = await text_to_speech(openai_client, answer)
                await message.answer_voice(BufferedInputFile(voice_bytes, filename="naum-answer.ogg"))
            except Exception:
                logger.exception("Не удалось отправить голосовой ответ")
        except Exception:
            logger.exception("Не удалось обработать голосовое сообщение")
            await message.answer(FAIL_TEXT)

    @dp.message(F.photo)
    async def photo_message(message: Message) -> None:
        try:
            photo = message.photo[-1]
            image = await download_telegram_file(bot, photo.file_id)
            caption = message.caption or ""
            async with db.session() as session:
                profile = await get_or_create_profile(session, message.from_user.id, settings.default_child_telegram_id)
                history = await get_history(session, message.from_user.id)
                answer = await analyze_photo(openai_client, image, "image/jpeg", caption, profile, history)
                user_text = f"Фото. Подпись: {caption}" if caption else "Фото без подписи"
                await add_message(session, message.from_user.id, "user", user_text)
                await add_message(session, message.from_user.id, "assistant", answer)
            await message.answer(answer)
        except Exception:
            logger.exception("Не удалось обработать фото")
            await message.answer(FAIL_TEXT)

    @dp.message(F.text)
    async def text_message(message: Message) -> None:
        text = message.text or ""
        try:
            async with db.session() as session:
                profile = await get_or_create_profile(session, message.from_user.id, settings.default_child_telegram_id)
                history = await get_history(session, message.from_user.id)
                safety = check_safety(text)
                if safety.needs_alert:
                    await notify_child(bot, profile, text)
                note = build_safety_note(text)
                answer = await openai_client.text_answer(text, profile, history, note)
                if safety.needs_alert and safety.emergency:
                    answer = urgent_user_message(True) + "\n\n" + answer
                await add_message(session, message.from_user.id, "user", text)
                await add_message(session, message.from_user.id, "assistant", answer)
            await message.answer(answer)
        except Exception:
            logger.exception("Не удалось обработать текстовое сообщение")
            await message.answer(FAIL_TEXT)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
