import base64
import inspect
import logging
from openai import AsyncOpenAI, OpenAIError

from config import Settings, load_naum_prompt
from db.models import ChatMessage, UserProfile
from services.profiles import profile_context

logger = logging.getLogger(__name__)


class NaumOpenAIClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.system_prompt = load_naum_prompt()

    def _ensure_client(self) -> AsyncOpenAI:
        if self.client is None:
            raise RuntimeError("OPENAI_API_KEY не задан")
        return self.client

    def _base_messages(self, profile: UserProfile, history: list[ChatMessage] | None = None) -> list[dict]:
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": profile_context(profile)},
        ]
        for item in history or []:
            messages.append({"role": item.role, "content": item.content})
        return messages

    async def text_answer(self, text: str, profile: UserProfile, history: list[ChatMessage] | None = None, safety_note: str | None = None) -> str:
        client = self._ensure_client()
        messages = self._base_messages(profile, history)
        if safety_note:
            messages.append({"role": "system", "content": safety_note})
        messages.append({"role": "user", "content": text})
        try:
            response = await client.chat.completions.create(
                model=self.settings.openai_text_model,
                messages=messages,
                temperature=0.7,
                max_tokens=500,
            )
            return response.choices[0].message.content or "Простите, я не смог подобрать ответ. Попробуйте ещё раз."
        except OpenAIError:
            logger.exception("Ошибка OpenAI при текстовом ответе")
            raise

    async def vision_answer(self, image_bytes: bytes, mime_type: str, caption: str, profile: UserProfile, history: list[ChatMessage] | None = None) -> str:
        client = self._ensure_client()
        data = base64.b64encode(image_bytes).decode("ascii")
        prompt = caption or "Посмотри на фото и объясни простыми словами: что видно, что это может быть, что делать дальше и когда нужна осторожность."
        messages = self._base_messages(profile, history)
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{data}"}},
                ],
            }
        )
        try:
            response = await client.chat.completions.create(
                model=self.settings.openai_vision_model,
                messages=messages,
                temperature=0.5,
                max_tokens=600,
            )
            return response.choices[0].message.content or "Фото вижу, но ответ не получился. Попробуйте прислать ещё раз."
        except OpenAIError:
            logger.exception("Ошибка OpenAI при анализе фото")
            raise

    async def transcribe(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        client = self._ensure_client()
        try:
            response = await client.audio.transcriptions.create(
                model=self.settings.openai_stt_model,
                file=(filename, audio_bytes),
            )
            return response.text
        except OpenAIError:
            logger.exception("Ошибка OpenAI при расшифровке голоса")
            raise

    async def synthesize(self, text: str) -> bytes:
        client = self._ensure_client()
        try:
            response = await client.audio.speech.create(
                model=self.settings.openai_tts_model,
                voice="alloy",
                input=text[:1200],
                response_format="opus",
            )
            content = response.read() if hasattr(response, "read") else getattr(response, "content", b"")
            if inspect.isawaitable(content):
                content = await content
            if not isinstance(content, bytes):
                content = bytes(content)
            return content
        except OpenAIError:
            logger.exception("Ошибка OpenAI при озвучивании ответа")
            raise
