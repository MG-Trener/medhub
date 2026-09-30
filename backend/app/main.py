import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from cryptography.fernet import Fernet
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, delete, text
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import Doctor, Session, ApiKey, Patient, Encounter, Job, Audit, db_session, now, uid, audit
from .security import current_doctor, integration_doctor, digest, passwords, search_tokens, registration_allowed, issue_session, owned
from .schemas import Register, Login, PatientInput, Consent, EncounterPatch, Consultation, PrivacyReview, Version, CloudAudio, MuteAudio
from .privacy import redact_segments
from .clinical import ai_notice
from .openai_asr import OPENAI_ASR_MODEL
from .identity import router as identity_router

app = FastAPI(title='medhub API', version='0.1.0', docs_url='/api/docs', openapi_url='/api/openapi.json')
app.include_router(identity_router)
rate_buckets = defaultdict(deque)
rate_lock = threading.Lock()


@app.middleware('http')
async def security_headers(request: Request, call_next):
    # Секреты сессии только в HttpOnly cookie; browser writes требуют CSRF header.
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and not request.url.path.startswith('/api/v1/integration/'):
        if request.headers.get('x-medhub-request') != '1' or request.headers.get('origin') not in (None, settings().public_origin):
            return JSONResponse({'detail': 'Недопустимый источник запроса'}, 403)
    if request.url.path.startswith('/api/v1/auth/'):
        key = request.client.host if request.client else 'unknown'
        current = time.monotonic()
        with rate_lock:
            for old in list(rate_buckets):
                if not rate_buckets[old] or rate_buckets[old][-1] < current - 60:
                    del rate_buckets[old]
            bucket = rate_buckets[key]
            while bucket and bucket[0] < current - 60:
                bucket.popleft()
            limit = 100 if request.method == 'GET' else 20
            if len(bucket) >= limit:
                return JSONResponse({'detail': 'Слишком много попыток. Подождите минуту'}, 429)
            bucket.append(current)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # FastAPI по умолчанию возвращает input, который может содержать пароль или ПДн.
    return JSONResponse({'detail': [{'loc': e['loc'], 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]}, 422)


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse({'detail': 'Запись с таким идентификатором уже существует'}, 409)


def patient_view(p):
    return {'id': p.id, **p.data, 'external_id': p.external_id, 'recording_consent': p.recording_consent, 'cloud_consent': p.cloud_consent, 'created_at': p.created_at}


def encounter_view(e):
    result = {k: getattr(e, k) for k in ('id', 'patient_id', 'status', 'recording_consent', 'transcript', 'redacted_transcript', 'fields', 'speaker_roles', 'privacy_reviewed', 'version', 'reviewed_at', 'created_at')}
    result['fields'] = Consultation.model_validate(e.fields).model_dump()
    result['ai_notice'] = ai_notice()
    return result


def verify_version(e, version):
    if e.version != version:
        raise HTTPException(409, 'Приём изменён. Обновите страницу перед сохранением')
    if e.status == 'processing':
        raise HTTPException(409, 'Дождитесь завершения обработки')


def queue(db, e, kind, payload=None):
    if e.status == 'processing':
        raise HTTPException(409, 'Обработка уже запущена')
    job = Job(encounter_id=e.id, kind=kind, payload={'version': e.version, 'previous_status': e.status, **(payload or {})})
    e.status = 'processing'
    db.add(job)
    audit(db, e.doctor_id, f'job.{kind}.queued', e.id)
    db.commit()
    return {'job_id': job.id}


@app.get('/api/health', tags=['Система'])
def health(db=Depends(db_session)):
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'service': 'medhub'}


@app.get('/api/v1/auth/options', tags=['Авторизация'])
def auth_options():
    return {'sigex_enabled': settings().sigex_enabled, 'demo_mode': settings().demo_mode}


@app.post('/api/v1/auth/register', tags=['Авторизация'], status_code=201)
def register(body: Register, response: Response, db=Depends(db_session)):
    registration_allowed(body.code)
    doctor = Doctor(login_hash=digest(body.email), identity_hash=digest('IIN' + body.iin),
        profile={'name': body.name, 'email': body.email, 'iin': body.iin, 'iin_verified': False},
        password_hash=passwords.hash(body.password))
    db.add(doctor)
    db.flush()
    issue_session(db, doctor, response)
    audit(db, doctor.id, 'doctor.register', doctor.id)
    db.commit()
    return {'id': doctor.id, **doctor.profile}


@app.post('/api/v1/auth/login', tags=['Авторизация'])
def login(body: Login, response: Response, db=Depends(db_session)):
    doctor = db.scalar(select(Doctor).where(Doctor.login_hash == digest(body.email)))
    try:
        if not doctor:
            passwords.hash(body.password)  # Сходная стоимость для неизвестного логина.
            raise VerifyMismatchError()
        passwords.verify(doctor.password_hash, body.password)
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(401, 'Неверный логин или пароль')
    issue_session(db, doctor, response)
    audit(db, doctor.id, 'doctor.login', doctor.id)
    db.commit()
    return {'id': doctor.id, **doctor.profile}


@app.post('/api/v1/auth/logout', tags=['Авторизация'])
def logout(request: Request, response: Response, db=Depends(db_session)):
    db.execute(delete(Session).where(Session.token_hash == digest(request.cookies.get('medhub_session', ''))))
    db.commit()
    response.delete_cookie('medhub_session')
    return {'ok': True}


@app.get('/api/v1/auth/me', tags=['Авторизация'])
def me(doctor=Depends(current_doctor)):
    return {'id': doctor.id, **doctor.profile}


@app.get('/api/v1/settings', tags=['Система'])
def configuration(doctor=Depends(current_doctor)):
    s = settings()
    return {'asr_provider': s.asr_provider, 'asr_model': OPENAI_ASR_MODEL if s.asr_provider == 'openai' else s.asr_model,
            'asr_configured': bool(s.openai_api_key.strip()) if s.asr_provider == 'openai' else s.asr_provider in ('self_hosted', 'faster_whisper'),
            'llm_provider': s.llm_provider, 'llm_model': s.llm_model, 'llm_is_cloud': s.llm_is_cloud,
            'diarization': s.asr_provider == 'openai' or bool(s.diarization_model), 'mis_configured': bool(s.mis_url),
            'cloud_asr_configured': bool(s.cloud_asr_url), 'audio_retention_hours': s.audio_retention_hours}


@app.get('/api/v1/patients', tags=['Пациенты'])
def patients(q: str = Query('', max_length=150), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), doctor=Depends(current_doctor), db=Depends(db_session)):
    stmt = select(Patient).where(Patient.doctor_id == doctor.id)
    if q:
        if re.fullmatch(r'\d{12}', q):
            stmt = stmt.where(Patient.iin_hash == digest(q))
        elif len(q.strip()) < 2:
            return []
        else:
            for word in re.findall(r'\w+', q.casefold()):
                stmt = stmt.where(Patient.search_tokens.contains(digest(word)))
    return [patient_view(p) for p in db.scalars(stmt.order_by(Patient.created_at.desc(), Patient.id).offset(offset).limit(limit))]


@app.post('/api/v1/patients', tags=['Пациенты'], status_code=201)
def create_patient(body: PatientInput, doctor=Depends(current_doctor), db=Depends(db_session)):
    p = Patient(doctor_id=doctor.id, iin_hash=digest(body.iin), search_tokens=search_tokens(body.name), external_id=body.external_id,
        recording_consent=body.recording_consent, cloud_consent=body.cloud_consent,
        data=body.model_dump(mode='json', exclude={'external_id', 'recording_consent', 'cloud_consent'}))
    db.add(p)
    db.flush()
    audit(db, doctor.id, 'patient.create', p.id)
    audit(db, doctor.id, 'consent.granted' if p.recording_consent else 'consent.refused', p.id)
    if body.openai_audio_consent:
        audit(db, doctor.id, 'consent.openai_audio.granted', p.id)
    db.commit()
    return patient_view(p)


@app.get('/api/v1/patients/{patient_id}', tags=['Пациенты'])
def get_patient(patient_id: str, doctor=Depends(current_doctor), db=Depends(db_session)):
    p = owned(db, Patient, patient_id, doctor)
    audit(db, doctor.id, 'patient.read', p.id)
    db.commit()
    return patient_view(p)


@app.patch('/api/v1/patients/{patient_id}/consent', tags=['Пациенты'])
def consent(patient_id: str, body: Consent, doctor=Depends(current_doctor), db=Depends(db_session)):
    p = owned(db, Patient, patient_id, doctor, True)
    p.recording_consent, p.cloud_consent = body.recording_consent, body.cloud_consent
    p.data = {**p.data, 'cloud_audio_consent': body.cloud_audio_consent, 'openai_audio_consent': body.openai_audio_consent}
    audit(db, doctor.id, 'consent.openai_audio.granted' if body.openai_audio_consent else 'consent.openai_audio.revoked', p.id)
    audit(db, doctor.id, 'consent.granted' if body.recording_consent else 'consent.revoked', p.id)
    # Отзыв действует также на уже созданные приёмы и будущие cloud-задания.
    for e in db.scalars(select(Encounter).where(Encounter.patient_id == p.id)):
        e.privacy_reviewed = False
        if not body.recording_consent:
            e.recording_consent = False
    db.commit()
    return patient_view(p)


@app.get('/api/v1/patients/{patient_id}/encounters', tags=['Приёмы'])
def patient_encounters(patient_id: str, doctor=Depends(current_doctor), db=Depends(db_session)):
    owned(db, Patient, patient_id, doctor)
    return [encounter_view(e) for e in db.scalars(select(Encounter).where(Encounter.patient_id == patient_id, Encounter.doctor_id == doctor.id).order_by(Encounter.created_at.desc()).limit(100))]


@app.post('/api/v1/patients/{patient_id}/encounters', tags=['Приёмы'], status_code=201)
def start_encounter(patient_id: str, doctor=Depends(current_doctor), db=Depends(db_session)):
    p = owned(db, Patient, patient_id, doctor)
    e = Encounter(doctor_id=doctor.id, patient_id=p.id, recording_consent=p.recording_consent, fields=Consultation().model_dump())
    db.add(e)
    db.flush()
    audit(db, doctor.id, 'encounter.start', e.id)
    db.commit()
    return encounter_view(e)


@app.get('/api/v1/encounters/{encounter_id}', tags=['Приёмы'])
def get_encounter(encounter_id: str, doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor)
    latest = db.scalar(select(Job).where(Job.encounter_id == e.id).order_by(Job.created_at.desc(), Job.id.desc()).limit(1))
    return {**encounter_view(e), 'last_job': {'state': latest.state, 'error': latest.error} if latest else None}


@app.patch('/api/v1/encounters/{encounter_id}', tags=['Приёмы'])
def edit_encounter(encounter_id: str, body: EncounterPatch, doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor, True)
    verify_version(e, body.version)
    e.fields = body.fields.model_dump()
    e.speaker_roles = body.speaker_roles
    if body.transcript is not None:
        e.transcript = [x.model_dump() for x in body.transcript]
        e.redacted_transcript = redact_segments(e.transcript, db.get(Patient, e.patient_id).data)
        e.privacy_reviewed = False
    e.status, e.reviewed_at = 'draft', None
    e.version += 1
    audit(db, doctor.id, 'encounter.edit', e.id)
    db.commit()
    return encounter_view(e)


@app.post('/api/v1/encounters/{encounter_id}/audio', tags=['Приёмы'], status_code=202)
async def upload_audio(encounter_id: str, file: UploadFile = File(...), doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor, True)
    p = db.get(Patient, e.patient_id)
    if not e.recording_consent or not p.recording_consent:
        raise HTTPException(403, 'Пациент не согласился на запись')
    if e.status == 'processing':
        raise HTTPException(409, 'Дождитесь завершения обработки')
    if settings().asr_provider in ('disabled', 'cloud'):
        raise HTTPException(503, 'Настройте локальное распознавание или доверенный ASR-сервер. Отправка исходного аудио в облако заблокирована.')
    if settings().asr_provider == 'openai':
        if not p.data.get('openai_audio_consent'):
            raise HTTPException(403, 'Нужно отдельное согласие пациента на передачу исходной записи в OpenAI. Укажите его в карте пациента.')
        if not settings().openai_api_key.strip():
            raise HTTPException(503, 'Добавьте OPENAI_API_KEY на сервере и перезапустите API и worker.')
    if (file.content_type or '').split(';')[0] not in ('audio/webm', 'audio/wav', 'audio/x-wav', 'audio/ogg', 'audio/mp4', 'video/webm', 'audio/mpeg'):
        raise HTTPException(415, 'Поддерживается WebM, WAV, OGG, MP4 или MP3')
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > settings().max_audio_mb * 1024 * 1024:
            raise HTTPException(413, 'Запись слишком большая')
    if len(data) < 32:
        raise HTTPException(422, 'Запись пуста')
    folder = Path(settings().audio_dir)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / (uid() + '.enc')
    path.write_bytes(Fernet(settings().encryption_key.encode()).encrypt(bytes(data)))
    try:
        return queue(db, e, 'transcribe', {'audio': path.name, 'asr_provider': settings().asr_provider})
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.post('/api/v1/encounters/{encounter_id}/privacy-review', tags=['Приёмы'])
def privacy_review(encounter_id: str, body: PrivacyReview, doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor, True)
    verify_version(e, body.version)
    e.redacted_transcript = redact_segments([x.model_dump() for x in body.segments], db.get(Patient, e.patient_id).data)
    e.privacy_reviewed = True
    e.version += 1
    audit(db, doctor.id, 'privacy.review', e.id)
    db.commit()
    return encounter_view(e)


def masked_audio_path(db, e):
    job = db.scalar(select(Job).where(Job.encounter_id == e.id, Job.kind == 'transcribe', Job.state == 'done').order_by(Job.created_at.desc(), Job.id.desc()).limit(1))
    name = job.payload.get('masked_audio') if job else None
    path = Path(settings().audio_dir) / Path(name).name if name else None
    if not path or not path.is_file():
        raise HTTPException(410, 'Обезличенная запись недоступна или удалена по сроку хранения')
    return path


@app.get('/api/v1/encounters/{encounter_id}/masked-audio', tags=['Приёмы'])
def listen_masked(encounter_id: str, doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor)
    if not e.recording_consent or not db.get(Patient, e.patient_id).recording_consent:
        raise HTTPException(403, 'Согласие на запись отозвано')
    data = Fernet(settings().encryption_key.encode()).decrypt(masked_audio_path(db, e).read_bytes())
    audit(db, doctor.id, 'audio.masked.read', e.id)
    db.commit()
    return Response(data, media_type='audio/wav', headers={'Content-Disposition': 'inline; filename="redacted.wav"'})


@app.post('/api/v1/encounters/{encounter_id}/mute-audio', tags=['Приёмы'], status_code=202)
def mute(encounter_id: str, body: MuteAudio, doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor, True)
    verify_version(e, body.version)
    if not e.recording_consent or not db.get(Patient, e.patient_id).recording_consent:
        raise HTTPException(403, 'Согласие на запись отозвано')
    if any(i < 0 or i >= len(e.transcript) for i in body.segment_indices):
        raise HTTPException(422, 'Некорректные номера реплик')
    return queue(db, e, 'mute_audio', {'masked_audio': masked_audio_path(db, e).name, 'indices': body.segment_indices})


@app.post('/api/v1/encounters/{encounter_id}/cloud-asr', tags=['Приёмы'], status_code=202)
def cloud_asr(encounter_id: str, body: CloudAudio, doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor, True)
    verify_version(e, body.version)
    p = db.get(Patient, e.patient_id)
    if not p.recording_consent or not e.recording_consent or not p.data.get('cloud_audio_consent') or not e.privacy_reviewed or not body.audio_reviewed:
        raise HTTPException(403, 'Нужны согласия пациента, проверка текста и прослушивание обезличенного аудио врачом')
    if not settings().cloud_asr_url:
        raise HTTPException(503, 'CLOUD_ASR_URL не настроен')
    return queue(db, e, 'cloud_asr', {'masked_audio': masked_audio_path(db, e).name})


@app.post('/api/v1/encounters/{encounter_id}/generate', tags=['Приёмы'], status_code=202)
def generate(encounter_id: str, body: Version, doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor, True)
    verify_version(e, body.version)
    if not e.transcript:
        raise HTTPException(422, 'Сначала добавьте расшифровку')
    if settings().llm_is_cloud and (not e.privacy_reviewed or not db.get(Patient, e.patient_id).cloud_consent):
        raise HTTPException(403, 'Для облачной LLM нужны согласие пациента и проверка маскирования врачом')
    return queue(db, e, 'generate')


@app.post('/api/v1/encounters/{encounter_id}/approve', tags=['Приёмы'])
def approve(encounter_id: str, body: Version, doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor, True)
    verify_version(e, body.version)
    if not any(v.strip() for v in e.fields.values()):
        raise HTTPException(422, 'Заполните лист консультации')
    e.status, e.reviewed_at = 'approved', now()
    e.version += 1
    audit(db, doctor.id, 'encounter.approve', e.id)
    db.commit()
    return encounter_view(e)


@app.get('/api/v1/jobs/{job_id}', tags=['Приёмы'])
def job_status(job_id: str, doctor=Depends(current_doctor), db=Depends(db_session)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, 'Задание не найдено')
    owned(db, Encounter, j.encounter_id, doctor)
    return {'id': j.id, 'state': j.state, 'kind': j.kind, 'error': j.error}


def export_view(db, e):
    p = db.get(Patient, e.patient_id)
    return {'schema_version': '1.0', 'encounter': encounter_view(e), 'patient': patient_view(p), 'doctor_id': e.doctor_id}


@app.post('/api/v1/encounters/{encounter_id}/send-to-mis', tags=['МИС'], status_code=202)
def send_mis(encounter_id: str, body: Version, doctor=Depends(current_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor, True)
    verify_version(e, body.version)
    if e.status not in ('approved', 'exported') or not e.reviewed_at:
        raise HTTPException(409, 'Сначала подтвердите лист консультации')
    if not settings().mis_url:
        raise HTTPException(503, 'MIS_URL не настроен. Доступна интеграция через API чтения')
    return queue(db, e, 'export')


@app.post('/api/v1/integration-key', tags=['МИС'])
def create_key(doctor=Depends(current_doctor), db=Depends(db_session)):
    token = 'mh_' + secrets.token_urlsafe(32)
    db.execute(delete(ApiKey).where(ApiKey.doctor_id == doctor.id))
    db.add(ApiKey(token_hash=digest(token), doctor_id=doctor.id))
    audit(db, doctor.id, 'integration.key.rotate', doctor.id)
    db.commit()
    return {'api_key': token, 'note': 'Сохраните ключ: он показывается один раз. Предыдущий ключ отозван.'}


@app.delete('/api/v1/integration-key', tags=['МИС'])
def revoke_key(doctor=Depends(current_doctor), db=Depends(db_session)):
    db.execute(delete(ApiKey).where(ApiKey.doctor_id == doctor.id))
    audit(db, doctor.id, 'integration.key.revoke', doctor.id)
    db.commit()
    return {'ok': True}


@app.get('/api/v1/integration/encounters', tags=['МИС'])
def integration_list(since: int = Query(0, ge=0), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), patient_id: str | None = None, doctor=Depends(integration_doctor), db=Depends(db_session)):
    q = select(Encounter).where(Encounter.doctor_id == doctor.id, Encounter.status.in_(['approved', 'exported']), Encounter.reviewed_at >= since)
    if patient_id:
        q = q.where(Encounter.patient_id == patient_id)
    rows = list(db.scalars(q.order_by(Encounter.reviewed_at, Encounter.id).offset(offset).limit(limit + 1)))
    items = [export_view(db, e) for e in rows[:limit]]
    audit(db, doctor.id, 'integration.list', doctor.id)
    db.commit()
    return {'items': items, 'next_offset': offset + limit if len(rows) > limit else None}


@app.get('/api/v1/integration/encounters/{encounter_id}', tags=['МИС'])
def integration_get(encounter_id: str, doctor=Depends(integration_doctor), db=Depends(db_session)):
    e = owned(db, Encounter, encounter_id, doctor)
    if e.status not in ('approved', 'exported'):
        raise HTTPException(404, 'Подтверждённый приём не найден')
    result = export_view(db, e)
    audit(db, doctor.id, 'integration.read', e.id)
    db.commit()
    return result


@app.get('/api/v1/audit', tags=['Система'])
def audit_log(doctor=Depends(current_doctor), db=Depends(db_session)):
    return [{'action': x.action, 'object_id': x.object_id, 'created_at': x.created_at} for x in db.scalars(select(Audit).where(Audit.doctor_id == doctor.id).order_by(Audit.created_at.desc()).limit(100))]
