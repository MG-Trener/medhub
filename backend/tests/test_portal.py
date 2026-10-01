import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.config import settings
from app.db import SessionLocal
from app.interview import default_script, select_followups


def register_patient(client, email='patient@example.test'):
    response = client.post('/api/v1/portal/auth/register', json={'email': email, 'password': 'Synthetic-password-123',
        'name': 'Тестовый Пациент', 'age': 28, 'sex': 'female', 'language': 'mixed', 'consent': True})
    assert response.status_code == 201, response.text
    return response.json()


def create(client, doctor, monkeypatch):
    monkeypatch.setattr(settings(), 'patient_portal_enabled', True)
    invitation = client.post('/api/v1/intake-invitations', json={}).json()['url'].split('#invite=')[1]
    register_patient(client)
    response = client.post('/api/v1/portal/intakes', json={'invitation': invitation, 'recording_consent': True})
    assert response.status_code == 201, response.text
    return response.json(), invitation


def test_ownership_encryption_invite_and_submit(client, doctor, monkeypatch):
    intake, invitation = create(client, doctor, monkeypatch)
    assert client.post('/api/v1/portal/intakes', json={'invitation': invitation}).status_code == 409
    other = TestClient(app, headers={'X-Medhub-Request': '1'})
    register_patient(other, 'other-patient@example.test')
    assert other.patch('/api/v1/portal/intakes/' + intake['id'], json={'version': 1, 'answers': {}}).status_code == 404
    assert other.get('/api/v1/auth/me').status_code == 401
    answers = {q['id']: 'Синтетический ответ без ПДн' for q in default_script()}
    saved = client.patch('/api/v1/portal/intakes/' + intake['id'], json={'version': 1, 'answers': answers, 'language': 'mixed'})
    assert saved.status_code == 200
    assert client.patch('/api/v1/portal/intakes/' + intake['id'], json={'version': 1, 'answers': answers}).status_code == 409
    with SessionLocal() as db:
        assert 'Синтетический' not in db.execute(text('SELECT data FROM patient_intakes')).scalar()
        assert 'Тестовый Пациент' not in db.execute(text('SELECT profile FROM portal_accounts LIMIT 1')).scalar()
    submitted = client.post('/api/v1/portal/intakes/' + intake['id'] + '/submit', json={'version': 2})
    assert submitted.status_code == 200 and submitted.json()['state'] == 'submitted'
    assert client.patch('/api/v1/portal/intakes/' + intake['id'], json={'version': 3, 'answers': answers}).status_code == 409
    inbox = client.get('/api/v1/intakes').json()
    assert len(inbox) == 1 and inbox[0]['patient_profile']['age'] == 28
    assert client.post('/api/v1/portal/intakes/' + intake['id'] + '/revoke', json={'version': 3}).status_code == 200


def test_script_before_adaptive_questions_and_urgent_stop(client, doctor, monkeypatch):
    intake, _ = create(client, doctor, monkeypatch)
    calls = []
    monkeypatch.setattr('app.portal.select_followups', lambda answers, clinical: calls.append(clinical) or ['pain_location'])
    assert client.post('/api/v1/portal/intakes/' + intake['id'] + '/followups', json={'version': 1}).status_code == 422
    answers = {q['id']: 'Жалоба / шағым' for q in default_script()}
    saved = client.patch('/api/v1/portal/intakes/' + intake['id'], json={'version': 1, 'answers': answers}).json()
    result = client.post('/api/v1/portal/intakes/' + intake['id'] + '/followups', json={'version': saved['version']})
    assert result.status_code == 200 and result.json()['data']['followups'] == ['pain_location']
    assert calls == [{'age': 28, 'sex': 'female'}]
    result = client.patch('/api/v1/portal/intakes/' + intake['id'], json={'version': result.json()['version'], 'answers': answers, 'urgent': True}).json()
    response = client.post('/api/v1/portal/intakes/' + intake['id'] + '/followups', json={'version': result['version']})
    assert response.json()['emergency'] and len(calls) == 1


def test_import_is_once_and_requires_doctor_ownership(client, doctor, monkeypatch):
    from test_workflow import patient, encounter
    intake, _ = create(client, doctor, monkeypatch)
    answers = {q['id']: 'Слова пациента' for q in default_script()}
    client.patch('/api/v1/portal/intakes/' + intake['id'], json={'version': 1, 'answers': answers})
    client.post('/api/v1/portal/intakes/' + intake['id'] + '/submit', json={'version': 2})
    e = encounter(client, patient(client))
    result = client.post('/api/v1/intakes/' + intake['id'] + '/import', json={'version': e['version'], 'encounter_id': e['id']})
    assert result.status_code == 200
    assert 'со слов пациента' in result.json()['fields']['anamnesis']
    assert result.json()['fields']['diagnosis'] == ''
    assert 'anamnesis' in result.json()['fields']['locked_fields']
    assert client.post('/api/v1/intakes/' + intake['id'] + '/import', json={'version': result.json()['version'], 'encounter_id': e['id']}).status_code == 409


def test_adaptive_model_can_only_select_known_questions(monkeypatch):
    monkeypatch.setattr('app.interview.structured_chat', lambda *args: '{"question_ids":["prescribe_drug","fever","sexual_history"]}')
    assert select_followups({'sexual_history': 'Пропустить'}, {'age': 30}) == ['fever']


def test_patient_voice_external_asr_is_blocked(client, doctor, monkeypatch):
    from audio_fixture import audio_bytes
    intake, _ = create(client, doctor, monkeypatch)
    monkeypatch.setattr(settings(), 'asr_provider', 'openai')
    response = client.post('/api/v1/portal/intakes/' + intake['id'] + '/voice', data={'version': 1},
        files={'file': ('answer.wav', audio_bytes(), 'audio/wav')})
    assert response.status_code == 503


def test_long_patient_voice_rejected_before_gpu(client, doctor, monkeypatch):
    import io
    import wave
    intake, _ = create(client, doctor, monkeypatch)
    monkeypatch.setattr(settings(), 'asr_provider', 'self_hosted')
    monkeypatch.setattr(settings(), 'asr_url', 'http://127.0.0.1:8090')
    def forbidden(*args):
        raise AssertionError('Long audio must never reach ASR')
    monkeypatch.setattr('app.portal.transcribe', forbidden)
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
        audio.writeframes(b'\0\0' * 16000 * 33)
    response = client.post('/api/v1/portal/intakes/' + intake['id'] + '/voice', data={'version': 1},
        files={'file': ('answer.wav', output.getvalue(), 'audio/wav')})
    assert response.status_code == 422
