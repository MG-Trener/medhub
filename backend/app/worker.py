"""Один worker в Compose: очередь хранится в PostgreSQL, ASR не блокирует HTTP."""
import logging
import tempfile
import time
from pathlib import Path
import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select
from .config import settings
from .db import SessionLocal, Job, Encounter, Patient, audit, now
from .privacy import redact_segments
from .providers import transcribe, generate, cloud_transcribe, ProviderError
from .audio_privacy import mask_audio
from .clinical import ai_notice

log = logging.getLogger('medhub.worker')


def process_one():
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.state == 'queued').order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:
            return False
        job.state, job.updated_at = 'running', now()
        db.commit()
        job_id, encounter_id, kind, payload = job.id, job.encounter_id, job.kind, job.payload
    audio_path = None
    masked_path = None
    try:
        with SessionLocal() as db:
            e = db.get(Encounter, encounter_id)
            p = db.get(Patient, e.patient_id)
            if e.version != payload['version']:
                raise ProviderError('Приём изменился. Запустите обработку повторно.')
            if kind == 'transcribe' and (not p.recording_consent or not e.recording_consent):
                raise ProviderError('Согласие на запись отозвано')
            if kind == 'transcribe':
                provider = settings().asr_provider
                if payload.get('asr_provider', 'legacy') != provider and (provider == 'openai' or 'asr_provider' in payload):
                    raise ProviderError('Провайдер распознавания изменился. Отправьте запись повторно.')
                if provider == 'openai' and not p.data.get('openai_audio_consent'):
                    raise ProviderError('Нет согласия на передачу исходной записи в OpenAI')
            if kind == 'generate' and settings().llm_is_cloud and (not p.cloud_consent or not e.privacy_reviewed):
                raise ProviderError('Нет согласия на облако или проверки маскирования')
            transcript = e.redacted_transcript
            original_segments = e.transcript
            if kind in ('mute_audio', 'cloud_asr') and (not p.recording_consent or not e.recording_consent):
                raise ProviderError('Согласие на запись отозвано')
            if kind == 'cloud_asr' and (not p.data.get('cloud_audio_consent') or not e.privacy_reviewed):
                raise ProviderError('Согласие на облако или проверка маскирования отсутствует')
            patient_data = p.data
            export = {'schema_version': '1.0', 'encounter': {k: getattr(e, k) for k in ('id', 'patient_id', 'fields', 'transcript', 'speaker_roles', 'reviewed_at', 'version', 'created_at')}, 'patient': {'id': p.id, 'external_id': p.external_id, **p.data}, 'doctor_id': e.doctor_id}
            export['encounter']['ai_notice'] = ai_notice()
            if kind == 'export' and not e.reviewed_at:
                raise ProviderError('Лист не подтверждён врачом')
        if kind == 'transcribe':
            audio_path = Path(settings().audio_dir) / Path(payload['audio']).name
            audio = Fernet(settings().encryption_key.encode()).decrypt(audio_path.read_bytes())
            with tempfile.TemporaryDirectory(prefix='medhub-audio-') as directory:
                decoded = Path(directory) / 'recording.audio'
                decoded.write_bytes(audio)
                result = transcribe(decoded)
                redacted = redact_segments(result, patient_data)
                indices = [i for i, (raw, masked) in enumerate(zip(result, redacted)) if raw['text'] != masked['text']]
                masked = mask_audio(decoded, result, indices)
                masked_path = audio_path.with_name(audio_path.stem + '.masked.enc')
                masked_path.write_bytes(Fernet(settings().encryption_key.encode()).encrypt(masked))
        elif kind == 'generate':
            result = generate(transcript)
        elif kind in ('mute_audio', 'cloud_asr'):
            path = Path(settings().audio_dir) / Path(payload['masked_audio']).name
            masked = Fernet(settings().encryption_key.encode()).decrypt(path.read_bytes())
            if kind == 'cloud_asr':
                result = cloud_transcribe(masked, original_segments)
            else:
                with tempfile.TemporaryDirectory(prefix='medhub-mute-') as directory:
                    decoded = Path(directory) / 'redacted.wav'
                    decoded.write_bytes(masked)
                    result = mask_audio(decoded, original_segments, payload['indices'])
                path.write_bytes(Fernet(settings().encryption_key.encode()).encrypt(result))
        elif kind == 'export':
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                response = client.post(settings().mis_url, json=export, headers={'Authorization': 'Bearer ' + settings().mis_token, 'Idempotency-Key': f'{encounter_id}:{payload["version"]}'})
                response.raise_for_status()
                if not 200 <= response.status_code < 300:
                    raise ProviderError('МИС не подтвердила приём данных')
            result = None
        else:
            raise ProviderError('Неизвестный тип задания')
        with SessionLocal() as db:
            e = db.scalar(select(Encounter).where(Encounter.id == encounter_id).with_for_update())
            p = db.get(Patient, e.patient_id)
            job = db.get(Job, job_id)
            if e.version != payload['version']:
                raise ProviderError('Приём был изменён во время обработки')
            if kind in ('transcribe', 'cloud_asr'):
                if not p.recording_consent or not e.recording_consent:
                    raise ProviderError('Согласие на запись отозвано. Результат удалён.')
                if kind == 'cloud_asr' and not p.data.get('cloud_audio_consent'):
                    raise ProviderError('Согласие на облачный ASR отозвано. Результат удалён.')
                if kind == 'transcribe' and payload.get('asr_provider') == 'openai' and not p.data.get('openai_audio_consent'):
                    raise ProviderError('Согласие на OpenAI отозвано. Результат удалён.')
                e.transcript = result
                e.redacted_transcript = redact_segments(result, patient_data)
                e.privacy_reviewed = False
                e.speaker_roles = {x['speaker']: 'unknown' for x in result}
                e.reviewed_at = None
                if kind == 'transcribe':
                    job.payload = {**job.payload, 'masked_audio': masked_path.name}
            elif kind == 'generate':
                if settings().llm_is_cloud and (not p.cloud_consent or not e.privacy_reviewed):
                    raise ProviderError('Согласие на облако отозвано. Результат удалён.')
                # Повторная генерация не заменяет диагноз, уже внесённый врачом.
                diagnosis = e.fields.get('diagnosis', '')
                e.fields = {**result['fields'], 'diagnosis': diagnosis or result['fields'].get('diagnosis', '')}
                e.speaker_roles = result['speaker_roles']
                e.reviewed_at = None
            elif kind == 'mute_audio':
                e.privacy_reviewed = False
                e.reviewed_at = None
            e.status = 'exported' if kind == 'export' else 'ready'
            # Отправка в МИС не меняет клиническую версию документа (idempotency).
            if kind != 'export':
                e.version += 1
            job.state, job.updated_at = 'done', now()
            audit(db, e.doctor_id, f'job.{kind}.done', e.id)
            db.commit()
    except Exception as error:
        if masked_path:
            masked_path.unlink(missing_ok=True)
        message = str(error) if isinstance(error, ProviderError) else 'Провайдер недоступен или вернул некорректный ответ. Проверьте настройки и повторите.'
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.state, job.error, job.updated_at = 'failed', message[:250], now()
            e = db.get(Encounter, encounter_id)
            if e.status == 'processing':
                e.status = payload.get('previous_status', 'draft')
            audit(db, e.doctor_id, f'job.{kind}.failed', e.id)
            db.commit()
        log.warning('job=%s failed type=%s', job_id, type(error).__name__)
    finally:
        if kind == 'transcribe':
            (Path(settings().audio_dir) / Path(payload['audio']).name).unlink(missing_ok=True)
    return True


def recover():
    # Единственный worker: прерванное внешнее действие не повторяется автоматически.
    with SessionLocal() as db:
        for job in db.scalars(select(Job).where(Job.state == 'running')):
            job.state, job.error = 'failed', 'Worker перезапущен. Повторите действие; МИС получает тот же ключ идемпотентности.'
            e = db.get(Encounter, job.encounter_id)
            e.status = job.payload.get('previous_status', 'draft')
        db.commit()


def cleanup():
    cutoff = now() - settings().audio_retention_hours * 3600
    for path in Path(settings().audio_dir).glob('*.enc'):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    recover()
    while True:
        try:
            cleanup()
            if not process_one():
                time.sleep(2)
        except Exception as error:
            log.error('worker failure type=%s', type(error).__name__)
            time.sleep(5)
