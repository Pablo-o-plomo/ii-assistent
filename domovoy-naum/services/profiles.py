from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ChatMessage, UserProfile

PROFILE_FIELDS = {
    "name": "Имя",
    "age": "Возраст",
    "city": "Город/станица",
    "illnesses": "Болезни (если хотите указать)",
    "medicines": "Лекарства (если хотите указать)",
    "allergies": "Аллергии",
    "children_names": "Имена детей",
    "child_telegram_id": "Telegram ID ребёнка",
    "interests": "Интересы",
}


async def get_or_create_profile(session: AsyncSession, telegram_id: int, default_child_id: int | None = None) -> UserProfile:
    profile = await session.get(UserProfile, telegram_id)
    if profile is None:
        profile = UserProfile(telegram_id=telegram_id, child_telegram_id=default_child_id)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if value in {"", "-", "нет", "Нет", "пропустить", "Пропустить"}:
        return None
    return value


async def update_profile_field(session: AsyncSession, profile: UserProfile, field: str, raw_value: str) -> None:
    value = _empty_to_none(raw_value)
    if field in {"age", "child_telegram_id"}:
        parsed = None
        if value is not None:
            digits = "".join(ch for ch in value if ch.isdigit() or ch == "-")
            parsed = int(digits) if digits and digits != "-" else None
        setattr(profile, field, parsed)
    else:
        setattr(profile, field, value)
    session.add(profile)
    await session.commit()


def format_profile(profile: UserProfile) -> str:
    lines = ["Вот что я запомнил:"]
    for field, title in PROFILE_FIELDS.items():
        value = getattr(profile, field)
        lines.append(f"• {title}: {value if value else 'не указано'}")
    return "\n".join(lines)


def profile_context(profile: UserProfile) -> str:
    parts = []
    for field, title in PROFILE_FIELDS.items():
        value = getattr(profile, field)
        if value:
            parts.append(f"{title}: {value}")
    return "Профиль пользователя:\n" + "\n".join(parts) if parts else "Профиль пользователя пока почти пуст."


async def add_message(session: AsyncSession, telegram_id: int, role: str, content: str) -> None:
    session.add(ChatMessage(telegram_id=telegram_id, role=role, content=content[:8000]))
    await session.commit()


async def get_history(session: AsyncSession, telegram_id: int, limit: int = 12) -> list[ChatMessage]:
    result = await session.execute(
        select(ChatMessage).where(ChatMessage.telegram_id == telegram_id).order_by(ChatMessage.created_at.desc()).limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def reset_history(session: AsyncSession, telegram_id: int) -> None:
    await session.execute(delete(ChatMessage).where(ChatMessage.telegram_id == telegram_id))
    await session.commit()
