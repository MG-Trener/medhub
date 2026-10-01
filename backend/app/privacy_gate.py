"""Автоматический локальный второй проход перед внешней LLM; ошибки закрывают egress."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import httpx
from .config import settings
from .ai_policy import trusted_url, llm_is_external
from .privacy import redact, redact_segments, redact_clinical_context, MASK
from .openai_asr import ProviderError


@lru_cache(maxsize=1)
def ner():
    path = Path(settings().privacy_ner_model)
    if not settings().privacy_ner_model or not path.is_dir():
        raise ProviderError('Настройте локальную модель защиты ПДн для автоматического анализа через API.')
    manifest = path / 'medhub-model-manifest.json'
    if not manifest.is_file():
        raise ProviderError('Требуется manifest локальной модели; используйте scripts/download_privacy_model.py.')
    checksums = json.loads(manifest.read_text(encoding='utf-8')).get('sha256', {})
    if not checksums:
        raise ProviderError('Пустой manifest модели защиты ПДн.')
    for name, expected in checksums.items():
        model_file = (path / name).resolve()
        if not model_file.is_relative_to(path.resolve()) or not model_file.is_file():
            raise ProviderError('Файлы модели защиты ПДн не соответствуют manifest.')
        with model_file.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != expected:
                raise ProviderError('Контрольная сумма модели защиты ПДн не совпадает.')
    from gliner import GLiNER
    return GLiNER.from_pretrained(str(path), local_files_only=True)


@lru_cache(maxsize=512)
def local_private_text(text):
    text = redact(text)
    if not text.strip():
        return text
    entities = []
    for offset in range(0, len(text), 700):
        chunk = text[offset:offset + 1000]
        found = ner().predict_entities(chunk, ['person', 'address', 'phone number', 'email',
            'national identification number', 'passport number', 'patient identifier'], threshold=0.3)
        entities.extend({**e, 'start': e['start'] + offset, 'end': e['end'] + offset} for e in found)
    spans = []
    for entity in sorted(entities, key=lambda e: (e['start'], e['end'])):
        a, b = entity['start'], entity['end']
        if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < b <= len(text)):
            raise ProviderError('Модель приватности вернула некорректные границы; внешний запрос отменён.')
        if spans and a <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(b, spans[-1][1]))
        else:
            spans.append((a, b))
    for a, b in reversed(spans):
        text = text[:a] + MASK + text[b:]
    return redact(text)


def automatic_privacy_ready():
    s = settings()
    return bool(s.privacy_ner_model or (s.privacy_service_url and s.privacy_service_token
                                      and trusted_url(s.privacy_service_url)))


def prepare_ai_input(segments, fields=None, patient=None):
    segments = redact_segments(segments, patient)
    context = redact_clinical_context(fields or {}, patient)
    if not llm_is_external():
        return segments, context
    if not automatic_privacy_ready():
        raise ProviderError('Облачный анализ ожидает автоматический локальный сервис защиты ПДн. Ручной просмотр не требуется; заполнение листа доступно.')
    # Склеиваем весь диалог для NER, затем отправляем безопасный текст как один контекст.
    # Источники клинического извлечения требуют исходных индексов, поэтому второй проход
    # отдельно получает также каждую реплику с окружением: если объединённая версия изменилась,
    # маскируем затронутые реплики полностью, сохраняя их таймкоды и номера.
    texts = [' '.join(x['text'] for x in segments)] + [x['text'] for x in segments]
    paths = []

    def collect(value, path=()):
        if isinstance(value, str):
            paths.append(path); texts.append(value)
        elif isinstance(value, dict):
            for key, item in value.items():
                collect(item, (*path, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                collect(item, (*path, index))
    collect(context)
    if settings().privacy_service_url:
        if not trusted_url(settings().privacy_service_url):
            raise ProviderError('Сервис защиты ПДн должен находиться внутри приватного контура.')
        with httpx.Client(timeout=90, follow_redirects=False) as client:
            response = client.post(settings().privacy_service_url.rstrip('/') + '/redact',
                json={'texts': texts}, headers={'Authorization': 'Bearer ' + settings().privacy_service_token})
            response.raise_for_status()
            safe = response.json().get('texts')
    else:
        safe = [local_private_text(text) for text in texts]
    if not isinstance(safe, list) or len(safe) != len(texts) or any(not isinstance(v, str) for v in safe):
        raise ProviderError('Автоматическая защита ПДн не завершена; внешний запрос отменён.')
    joined_safe = safe[0]
    result = []
    for i, segment in enumerate(segments):
        value = safe[i + 1]
        if segment['text'] and segment['text'] not in joined_safe and value == segment['text']:
            value = MASK  # Идентификатор обнаружен только с соседними репликами.
        result.append({**segment, 'text': redact(value, patient)})
    for path, value in zip(paths, safe[len(segments) + 1:]):
        target = context
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = redact(value, patient)
    return result, context
