from db.models import ChatMessage, UserProfile
from services.openai_client import NaumOpenAIClient


async def analyze_photo(
    openai_client: NaumOpenAIClient,
    image_bytes: bytes,
    mime_type: str,
    caption: str,
    profile: UserProfile,
    history: list[ChatMessage] | None = None,
) -> str:
    return await openai_client.vision_answer(image_bytes, mime_type, caption, profile, history)
