from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://medhub:medhub@localhost:5432/medhub'
    database_pool_size: int = 2
    database_max_overflow: int = 0
    encryption_key: str = ''
    index_key: str = ''
    public_origin: str = 'http://localhost:5173'
    secure_cookies: bool = False
    demo_mode: bool = False
    registration_code: str = ''
    audio_dir: str = './data/audio'
    max_audio_mb: int = 80
    audio_retention_hours: int = 0  # 0 — постоянное хранение записей приёмов
    asr_provider: str = 'disabled'  # faster_whisper, self_hosted, openai
    openai_api_key: str = ''
    asr_url: str = ''
    asr_api_key: str = ''
    asr_model: str = 'large-v3'
    asr_device: str = 'cpu'
    asr_compute_type: str = 'int8'
    asr_timeout_seconds: int = 1800
    cloud_asr_url: str = ''
    cloud_asr_api_key: str = ''
    cloud_asr_model: str = 'whisper-1'
    diarization_model: str = ''  # локальный каталог Community-1
    llm_provider: str = 'disabled'  # openai, ollama, openai_compatible
    llm_url: str = 'http://host.docker.internal:11434'
    llm_api_key: str = ''
    llm_model: str = 'qwen3:8b'
    llm_is_cloud: bool = False
    sigex_enabled: bool = True
    sigex_url: str = 'https://sigex.kz'
    mis_url: str = ''
    mis_token: str = ''


@lru_cache
def settings():
    return Settings()
