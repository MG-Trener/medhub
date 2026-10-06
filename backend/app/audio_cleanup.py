"""Редкая очистка только старых файлов, не связанных с заданиями приёмов."""
import time
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .db import Job, SessionLocal, now

CLEANUP_INTERVAL_SECONDS = 3600
_next_cleanup = 0.0


def cleanup():
    cutoff = now() - 24 * 3600
    candidates = {}
    for path in Path(settings().audio_dir).glob('*.enc'):
        try:
            if path.stat().st_mtime < cutoff:
                candidates[path.name] = path
        except FileNotFoundError:
            continue
    if not candidates:
        return

    # payload зашифрован целиком: извлечь ссылки SQL JSON-оператором нельзя.
    # Не загружаем остальные столбцы и ORM-объекты; читаем архив только раз в час.
    with SessionLocal() as db:
        payloads = db.scalars(select(Job.payload).where(Job.kind.in_(
            ['transcribe', 'mute_audio', 'cloud_asr', 'live_chunk']
        )).execution_options(yield_per=100))
        for payload in payloads:
            for key in ('audio', 'masked_audio'):
                if payload.get(key):
                    candidates.pop(Path(payload[key]).name, None)
            if not candidates:
                break

    # При ошибке чтения/расшифровки до удаления не доходим: архив сохраняется.
    for path in candidates.values():
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            continue


def cleanup_if_due():
    global _next_cleanup
    tick = time.monotonic()
    if tick < _next_cleanup:
        return
    # Ошибка БД тоже не должна вызывать повторное чтение каждые несколько секунд.
    _next_cleanup = tick + CLEANUP_INTERVAL_SECONDS
    cleanup()
