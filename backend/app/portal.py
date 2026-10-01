"""Пациентский кабинет не использует врачебную сессию и не открывает медкарту по ИИН."""
import secrets
import re
import tempfile
from pathlib import Path
from typing import Literal
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, Request, Response, HTTPException, UploadFile, File, Form
from pydantic import Field
from sqlalchemy import select, delete
from starlette.concurrency import run_in_threadpool
from .config import settings
from .db import PortalAccount, PortalSession, Intake, IntakeInvite, Encounter, Patient, db_session, now, audit
from .security import digest, passwords, current_doctor, owned
from .schemas import Strict, Login, Consultation, Version
from .privacy import redact
from .privacy_gate import prepare_ai_input
from .ai_policy import llm_is_external, require_trusted_asr
from .providers import transcribe, ProviderError
from .interview import default_script, FOLLOWUPS, select_followups

router = APIRouter(prefix='/api/v1', tags=['Кабинет пациента'])
CONSENT_VERSION = 'portal-2026-10-02.1'


def enabled():
    if not settings().patient_portal_enabled:
        raise HTTPException(503, 'Кабинет пациента пока не подключён')


def account(request: Request, db=Depends(db_session)):
    enabled()
    session = db.get(PortalSession, digest(request.cookies.get('medhub_patient_session', '')))
    if not session or session.expires_at <= now():
        raise HTTPException(401, 'Войдите в кабинет пациента')
    return db.get(PortalAccount, session.account_id)


def issue(db, row, response):
    token = secrets.token_urlsafe(32)
    age = settings().portal_session_hours * 3600
    db.add(PortalSession(token_hash=digest(token), account_id=row.id, expires_at=now() + age))
    response.set_cookie('medhub_patient_session', token, httponly=True,
        secure=settings().secure_cookies, samesite='strict', max_age=age, path='/')


def own_intake(db, intake_id, patient_account, lock=False):
    query = select(Intake).where(Intake.id == intake_id, Intake.account_id == patient_account.id)
    row = db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if not row:
        raise HTTPException(404, 'Анкета не найдена')
    return row


def versioned(row, version):
    if row.version != version:
        raise HTTPException(409, 'Анкета изменилась. Обновите страницу')
    if row.state != 'draft':
        raise HTTPException(409, 'Анкета уже отправлена врачу')


def view(row):
    return {'id': row.id, 'version': row.version, 'state': row.state, 'data': row.data,
            'created_at': row.created_at, 'updated_at': row.updated_at}


class Registration(Strict):
    email: str = Field(min_length=5, max_length=150, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=2, max_length=150)
    age: int = Field(ge=18, le=120)
    sex: Literal['female', 'male', 'unknown'] = 'unknown'
    language: Literal['ru', 'kk', 'mixed'] = 'ru'
    consent: bool


@router.get('/portal/options')
def options():
    return {'enabled': settings().patient_portal_enabled, 'consent_version': CONSENT_VERSION,
            'languages': ['ru', 'kk', 'mixed'], 'adult_only': True}


@router.post('/portal/auth/register', status_code=201)
def register(body: Registration, response: Response, db=Depends(db_session)):
    enabled()
    if not body.consent:
        raise HTTPException(403, 'Нужно согласие на хранение анкеты для передачи выбранному врачу')
    row = PortalAccount(login_hash=digest('portal:' + body.email), password_hash=passwords.hash(body.password),
        profile={**body.model_dump(exclude={'password', 'consent'}),
                 'consent_version': CONSENT_VERSION, 'consent_at': now()})
    db.add(row); db.flush(); issue(db, row, response)
    audit(db, row.id, 'portal.register', row.id); db.commit()
    return {'id': row.id, **row.profile}


@router.post('/portal/auth/login')
def login(body: Login, response: Response, db=Depends(db_session)):
    enabled()
    row = db.scalar(select(PortalAccount).where(PortalAccount.login_hash == digest('portal:' + body.email)))
    try:
        if not row:
            passwords.hash(body.password)
            raise VerificationError()
        passwords.verify(row.password_hash, body.password)
    except VerificationError:
        raise HTTPException(401, 'Неверный логин или пароль') from None
    issue(db, row, response); audit(db, row.id, 'portal.login', row.id); db.commit()
    return {'id': row.id, **row.profile}


@router.get('/portal/auth/me')
def me(row=Depends(account)):
    return {'id': row.id, **row.profile}


@router.post('/portal/auth/logout')
def logout(request: Request, response: Response, db=Depends(db_session)):
    db.execute(delete(PortalSession).where(PortalSession.token_hash == digest(request.cookies.get('medhub_patient_session', ''))))
    db.commit(); response.delete_cookie('medhub_patient_session', path='/')
    return {'ok': True}


class ScriptQuestion(Strict):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,49}$')
    ru: str = Field(min_length=3, max_length=1000)
    kk: str = Field(min_length=3, max_length=1000)


class Invitation(Strict):
    questions: list[ScriptQuestion] = Field(default_factory=list, max_length=30)


@router.post('/intake-invitations', status_code=201)
def invite(body: Invitation, doctor=Depends(current_doctor), db=Depends(db_session)):
    enabled()
    script = [q.model_dump() for q in body.questions] or default_script()
    if len({q['id'] for q in script}) != len(script):
        raise HTTPException(422, 'Номера вопросов должны быть уникальными')
    token = secrets.token_urlsafe(32)
    db.add(IntakeInvite(token_hash=digest(token), doctor_id=doctor.id, script={'questions': script}, expires_at=now() + 7 * 86400))
    audit(db, doctor.id, 'portal.invitation', doctor.id); db.commit()
    # Fragment не попадает в access logs/Referer. Ссылка одноразовая, не привязывает медкарту.
    return {'url': settings().public_origin + '/patient#invite=' + token, 'expires_in_days': 7}


class Start(Strict):
    invitation: str = Field(min_length=32, max_length=100)
    recording_consent: bool = False
    cloud_consent: bool = False


@router.post('/portal/intakes', status_code=201)
def start(body: Start, row=Depends(account), db=Depends(db_session)):
    invite = db.scalar(select(IntakeInvite).where(IntakeInvite.token_hash == digest(body.invitation)).with_for_update())
    if not invite or invite.expires_at <= now():
        raise HTTPException(404, 'Приглашение истекло или не найдено')
    if invite.account_id:
        raise HTTPException(409, 'Приглашение уже использовано')
    invite.account_id = row.id
    intake = Intake(account_id=row.id, doctor_id=invite.doctor_id, data={'questions': invite.script['questions'],
        'answers': {}, 'followups': [], 'followup_status': 'pending', 'language': row.profile['language'],
        'recording_consent': body.recording_consent, 'cloud_consent': body.cloud_consent,
        'consent_version': CONSENT_VERSION, 'consent_at': now(), 'urgent': False})
    db.add(intake); db.flush(); audit(db, row.id, 'portal.intake.create', intake.id); db.commit()
    return view(intake)


@router.get('/portal/intakes')
def list_intakes(row=Depends(account), db=Depends(db_session)):
    return [view(i) for i in db.scalars(select(Intake).where(Intake.account_id == row.id).order_by(Intake.created_at.desc()).limit(50))]


class Answers(Version):
    answers: dict[str, str] = Field(max_length=50)
    language: Literal['ru', 'kk', 'mixed'] = 'ru'
    urgent: bool = False  # явный ответ пациента на отдельный вопрос о неотложных симптомах


@router.patch('/portal/intakes/{intake_id}')
def save(intake_id: str, body: Answers, row=Depends(account), db=Depends(db_session)):
    intake = own_intake(db, intake_id, row, True); versioned(intake, body.version)
    valid = {q['id'] for q in intake.data['questions']} | set(intake.data.get('followups', []))
    if set(body.answers) - valid or any(len(v) > 5000 for v in body.answers.values()):
        raise HTTPException(422, 'Ответы должны соответствовать вопросам и быть не длиннее 5000 символов')
    # Узкие явные сигналы дополняют самостоятельную отметку пациента. Это не полный триаж.
    emergency_phrases = r'не могу дышать|задыхаюсь|сильная боль в груди|неостанавливаемое кровотечение|тыныс ала алмай|дем ала алмай|кеудем қатты ауырады'
    urgent_text = any(re.search(emergency_phrases, sentence, re.I) and not re.search(r'нет|жоқ|не было', sentence, re.I)
        for value in body.answers.values() for sentence in re.split(r'[.!?\n]', value))
    intake.data = {**intake.data, 'answers': body.answers, 'language': body.language,
                   'urgent': intake.data.get('urgent', False) or body.urgent or urgent_text}
    intake.version += 1; intake.updated_at = now()
    audit(db, row.id, 'portal.intake.save', intake.id); db.commit()
    return view(intake)


@router.post('/portal/intakes/{intake_id}/followups')
def followups(intake_id: str, body: Version, row=Depends(account), db=Depends(db_session)):
    intake = own_intake(db, intake_id, row, True); versioned(intake, body.version)
    if intake.data.get('urgent'):
        return {**view(intake), 'emergency': True, 'numbers': ['103', '112']}
    answers = dict(intake.data['answers'])
    if any(not answers.get(q['id'], '').strip() for q in intake.data['questions']):
        raise HTTPException(422, 'Сначала ответьте на все вопросы сценария; можно написать «пропустить»')
    if intake.data.get('followup_status') == 'done':
        return view(intake)
    if intake.data.get('followup_status') == 'running' and intake.updated_at > now() - 180:
        raise HTTPException(409, 'Уточнения уже формируются')
    if llm_is_external() and not intake.data.get('cloud_consent'):
        raise HTTPException(403, 'Для этой модели нужно согласие на обработку обезличенного анамнеза через API')
    intake.data = {**intake.data, 'followup_status': 'running'}
    intake.updated_at = now()
    expected, intake_data, profile = intake.version, dict(intake.data), dict(row.profile)
    db.commit()  # Не держим row lock во время inference; проверяем версию после.
    try:
        keys = list(answers)
        segments = [{'speaker': 'SPEAKER_00', 'start': i, 'end': i + 1, 'text': answers[key]} for i, key in enumerate(keys)]
        safe, _ = prepare_ai_input(segments, {}, profile)
        selected = select_followups(dict(zip(keys, (s['text'] for s in safe))), {'age': profile['age'], 'sex': profile['sex']})
    except Exception:
        db.rollback()
        latest = own_intake(db, intake_id, row, True)
        if latest.version == expected and latest.state == 'draft':
            latest.data = {**latest.data, 'followup_status': 'pending'}
            db.commit()
        raise HTTPException(503, 'Уточнения ИИ временно недоступны. Анкета сохранена; её можно отправить врачу.') from None
    intake = own_intake(db, intake_id, row, True); versioned(intake, expected)
    # Отзыв согласия/изменение ответов во время inference не допускают сохранение результата.
    intake.data = {**intake_data, 'followups': selected, 'followup_status': 'done'}
    intake.version += 1; intake.updated_at = now(); audit(db, row.id, 'portal.followups', intake.id); db.commit()
    return view(intake)


@router.post('/portal/intakes/{intake_id}/voice')
async def voice(intake_id: str, version: int = Form(..., ge=1), file: UploadFile = File(...),
                row=Depends(account), db=Depends(db_session)):
    intake = own_intake(db, intake_id, row); versioned(intake, version)
    if not intake.data.get('recording_consent') or intake.data.get('urgent'):
        raise HTTPException(403, 'Голосовая обработка не разрешена')
    try:
        require_trusted_asr()
    except ProviderError as error:
        raise HTTPException(503, str(error)) from None
    data = await file.read(4 * 1024 * 1024 + 1)
    if len(data) < 32 or len(data) > 4 * 1024 * 1024:
        raise HTTPException(413, 'Запишите короткий ответ до 4 МБ')
    from .lifecycle import audio_signature_valid
    mime = (file.content_type or '').split(';')[0]
    if not await run_in_threadpool(audio_signature_valid, data, mime):
        raise HTTPException(422, 'Нужна аудиозапись поддерживаемого формата')
    def recognize():
        with tempfile.TemporaryDirectory(prefix='medhub-portal-') as folder:
            path = Path(folder) / 'answer.audio'; path.write_bytes(data)
            return transcribe(path)
    try:
        segments = await run_in_threadpool(recognize)
    except Exception:
        raise HTTPException(503, 'Распознавание недоступно. Можно ответить текстом.') from None
    intake = own_intake(db, intake_id, row, True); versioned(intake, version)
    if not intake.data.get('recording_consent'):
        raise HTTPException(403, 'Согласие отозвано')
    # Исходный звук не сохраняется после локального ASR и не отправляется во внешний API.
    from .privacy import redact_segments
    safe = redact_segments(segments, row.profile)
    return {'text': ' '.join(s['text'] for s in safe), 'version': intake.version}


@router.post('/portal/intakes/{intake_id}/submit')
def submit(intake_id: str, body: Version, row=Depends(account), db=Depends(db_session)):
    intake = own_intake(db, intake_id, row, True); versioned(intake, body.version)
    if not intake.data['answers']:
        raise HTTPException(422, 'Добавьте ответы')
    if not intake.data.get('urgent') and any(not intake.data['answers'].get(q['id'], '').strip() for q in intake.data['questions']):
        raise HTTPException(422, 'Ответьте на обязательные вопросы или укажите «пропустить»')
    intake.state = 'submitted'; intake.version += 1; intake.updated_at = now()
    audit(db, row.id, 'portal.intake.submit', intake.id); db.commit()
    return view(intake)


@router.post('/portal/intakes/{intake_id}/revoke')
def revoke(intake_id: str, body: Version, row=Depends(account), db=Depends(db_session)):
    intake = own_intake(db, intake_id, row, True)
    if intake.version != body.version:
        raise HTTPException(409, 'Анкета изменилась')
    intake.data = {**intake.data, 'recording_consent': False, 'cloud_consent': False}
    intake.version += 1; audit(db, row.id, 'portal.consent.revoke', intake.id); db.commit()
    return view(intake)


@router.get('/intakes')
def doctor_intakes(doctor=Depends(current_doctor), db=Depends(db_session)):
    records = db.scalars(select(Intake).where(Intake.doctor_id == doctor.id, Intake.state.in_(['submitted', 'imported'])).order_by(Intake.updated_at.desc()).limit(100))
    return [{**view(i), 'patient_profile': db.get(PortalAccount, i.account_id).profile} for i in records]


class Import(Version):
    encounter_id: str = Field(max_length=36)


@router.post('/intakes/{intake_id}/import')
def import_intake(intake_id: str, body: Import, doctor=Depends(current_doctor), db=Depends(db_session)):
    intake = owned(db, Intake, intake_id, doctor, True)
    e = owned(db, Encounter, body.encounter_id, doctor, True)
    from .main import verify_version, encounter_view
    verify_version(e, body.version)
    if intake.state != 'submitted' or intake.encounter_id:
        raise HTTPException(409, 'Анкета уже перенесена или не отправлена')
    # Сопоставление с медкартой выполняет врач; логин/ИИН не открывают чужую карту.
    sections = []
    questions = {q['id']: q['ru'] for q in intake.data['questions']}
    questions.update({key: ru for key, ru, _ in FOLLOWUPS})
    for key, value in intake.data['answers'].items():
        sections.append(f'{questions.get(key, key)}\n{value}')
    report = 'Предварительная анкета, со слов пациента.\n' + '\n\n'.join(sections)
    existing = Consultation.model_validate(e.fields).model_dump()
    merged = existing['anamnesis'] + ('\n\n' if existing['anamnesis'] else '') + report
    if len(merged) > 15000:
        raise HTTPException(422, 'Анкета слишком длинная для поля; просмотрите её отдельно')
    existing['anamnesis'] = merged
    existing['locked_fields'] = sorted(set(existing['locked_fields']) | {'anamnesis'})
    existing['reviewed_fields'] = [k for k in existing['reviewed_fields'] if k != 'anamnesis']
    existing['sources'] = [s for s in existing['sources'] if s['field'] != 'anamnesis']
    e.fields = existing; e.version += 1; e.reviewed_at = None; e.privacy_reviewed = False; e.status = 'draft'
    intake.encounter_id, intake.state = e.id, 'imported'
    intake.version += 1
    from .history import snapshot
    snapshot(db, e, 'intake_import'); audit(db, doctor.id, 'portal.intake.import', intake.id); db.commit()
    return encounter_view(e, db, doctor)
