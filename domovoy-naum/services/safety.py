import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyResult:
    needs_alert: bool
    emergency: bool
    reason: str | None = None


ALERT_PATTERNS = [
    r"мне\s+очень\s+плохо",
    r"я\s+упал[а]?(?:\b|\s)",
    r"не\s+могу\s+встать",
    r"давлени[ея]\s+.*(?:18\d|19\d|2\d\d|очень\s+высок)",
    r"мне\s+страшно",
    r"не\s+хочу\s+жить",
    r"сильн\w*\s+боль\s+в\s+груди",
    r"тяжело\s+дышать",
    r"боль\s+в\s+груди",
    r"задыхаюсь",
    r"кровь",
    r"инсульт",
    r"потерял[а]?\s+сознание",
    r"спутанн\w*\s+реч",
    r"самоповрежд",
]

EMERGENCY_PATTERNS = [
    r"не\s+хочу\s+жить",
    r"самоповрежд",
    r"сильн\w*\s+боль\s+в\s+груди",
    r"боль\s+в\s+груди",
    r"тяжело\s+дышать",
    r"задыхаюсь",
    r"давлени[ея]\s+.*(?:18\d|19\d|2\d\d)",
    r"инсульт",
    r"потерял[а]?\s+сознание",
    r"спутанн\w*\s+реч",
]

SUPPORT_PATTERNS = [
    r"мне\s+грустно",
    r"никому\s+не\s+нуж",
    r"дети\s+далеко",
    r"не\s+могу\s+помочь\s+детям",
    r"мне\s+тревожно",
    r"мне\s+одиноко",
    r"я\s+устал[а]?",
    r"жизнь\s+стала\s+пустой",
]


def _matches(patterns: list[str], text: str) -> str | None:
    normalized = text.lower()
    for pattern in patterns:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return pattern
    return None


def check_safety(text: str) -> SafetyResult:
    emergency_reason = _matches(EMERGENCY_PATTERNS, text)
    alert_reason = _matches(ALERT_PATTERNS, text)
    return SafetyResult(needs_alert=bool(alert_reason or emergency_reason), emergency=bool(emergency_reason), reason=alert_reason or emergency_reason)


def needs_emotional_support(text: str) -> bool:
    return _matches(SUPPORT_PATTERNS, text) is not None


def urgent_user_message(emergency: bool) -> str:
    if emergency:
        return (
            "Родной человек, сейчас лучше не ждать. Если есть боль в груди, тяжело дышать, сильная слабость, "
            "очень высокое давление или мысли навредить себе — пожалуйста, позвоните в скорую 112 или 103. "
            "Если можете, сядьте или лягте безопасно, откройте дверь/сообщите близким и держите телефон рядом."
        )
    return (
        "Я рядом и слышу вас. Пожалуйста, сядьте поудобнее, проверьте, нет ли травмы, и позвоните близкому человеку. "
        "Если состояние ухудшается или вы не можете встать — звоните 112 или 103."
    )
