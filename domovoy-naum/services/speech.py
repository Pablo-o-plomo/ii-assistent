from services.openai_client import NaumOpenAIClient


async def speech_to_text(openai_client: NaumOpenAIClient, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    return await openai_client.transcribe(audio_bytes, filename)


async def text_to_speech(openai_client: NaumOpenAIClient, text: str) -> bytes:
    return await openai_client.synthesize(text)
