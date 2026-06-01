from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    telegram_bot_token: str
    openai_api_key: str = ""
    openai_text_model: str = "gpt-4o-mini"
    openai_vision_model: str = "gpt-4o-mini"
    openai_stt_model: str = "whisper-1"
    openai_tts_model: str = "tts-1"
    database_url: str = "sqlite+aiosqlite:///./naum.db"
    default_child_telegram_id: int | None = None

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("default_child_telegram_id", mode="before")
    @classmethod
    def empty_child_id_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_naum_prompt() -> str:
    return (BASE_DIR / "prompts" / "naum_system_prompt.txt").read_text(encoding="utf-8")
