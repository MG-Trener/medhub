from fastapi.testclient import TestClient
from app.main import app
from app.db import Doctor, Session, engine
from sqlalchemy.orm import Session as DbSession
from app.security import digest

OLD = 'Very-safe-test-123'
NEW = 'Updated-password-456'


def password_body(**changes):
    return {'new_password': NEW, 'confirm_password': NEW, **changes}


def test_profile_requires_session_and_csrf(client):
    assert client.patch('/api/v1/auth/profile', json={'email': 'new@example.test', 'phone': ''}).status_code == 401
    assert client.post('/api/v1/auth/password', json=password_body()).status_code == 401
    with TestClient(app) as anonymous:
        assert anonymous.patch('/api/v1/auth/profile', json={'email': 'new@example.test', 'phone': ''}).status_code == 403


def test_contacts_update_login_and_preserve_identity(client, doctor):
    result = client.patch('/api/v1/auth/profile', json={'email': ' New@Example.test ', 'phone': '+7 (701) 123-45-67'})
    assert result.status_code == 200, result.text
    profile = result.json()
    assert profile['email'] == 'new@example.test' and profile['phone'] == '+77011234567'
    assert profile['iin'] == doctor['iin'] and profile['name'] == doctor['name']
    assert profile['iin_verified'] == doctor['iin_verified']
    assert client.get('/api/v1/auth/me').json() == profile
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert client.post('/api/v1/auth/login', json={'email': doctor['email'], 'password': OLD}).status_code == 401
    assert client.post('/api/v1/auth/login', json={'email': 'NEW@example.test', 'password': OLD}).json()['id'] == doctor['id']
    assert client.patch('/api/v1/auth/profile', json={'email': 'new@example.test', 'phone': ''}).json()['phone'] == ''


def test_profile_rejects_invalid_contacts_and_identity_changes(client, doctor):
    for body in [
        {'email': 'bad', 'phone': ''},
        {'email': 'new@example.test', 'phone': '123'},
        {'email': 'new@example.test', 'phone': '', 'iin': '000000000002'},
    ]:
        assert client.patch('/api/v1/auth/profile', json=body).status_code == 422
    assert client.get('/api/v1/auth/me').json() == doctor


def test_email_collision_keeps_both_accounts_unchanged(client, doctor):
    with TestClient(app, headers={'X-Medhub-Request': '1'}) as other:
        second = other.post('/api/v1/auth/register', json={'name': 'Second doctor', 'iin': '000000000002', 'email': 'other@example.test', 'password': OLD}).json()
        result = client.patch('/api/v1/auth/profile', json={'email': 'OTHER@example.test', 'phone': ''})
        assert result.status_code == 409
        assert client.get('/api/v1/auth/me').json() == doctor
        assert other.get('/api/v1/auth/me').json() == second


def test_password_change_rotates_all_sessions_and_keeps_current(client, doctor):
    with TestClient(app, headers={'X-Medhub-Request': '1'}) as other:
        assert other.post('/api/v1/auth/login', json={'email': doctor['email'], 'password': OLD}).status_code == 200
        old_cookie = client.cookies.get('medhub_session')
        result = client.post('/api/v1/auth/password', json=password_body())
        assert result.status_code == 200, result.text
        assert client.cookies.get('medhub_session') != old_cookie
        assert client.get('/api/v1/auth/me').json()['id'] == doctor['id']
        assert other.get('/api/v1/auth/me').status_code == 401
        with DbSession(engine) as db:
            assert db.get(Session, digest(old_cookie)) is None
            stored = db.get(Doctor, doctor['id'])
            assert stored.password_hash not in (OLD, NEW)
            assert stored.identity_hash == digest('IIN' + doctor['iin'])
        assert other.post('/api/v1/auth/login', json={'email': doctor['email'], 'password': OLD}).status_code == 401
        assert other.post('/api/v1/auth/login', json={'email': doctor['email'], 'password': NEW}).status_code == 200


def test_password_validation_does_not_change_account(client, doctor):
    for body, status in [
        (password_body(confirm_password='Does-not-match-123'), 422),
        (password_body(new_password='tiny123', confirm_password='tiny123'), 422),
    ]:
        result = client.post('/api/v1/auth/password', json=body)
        assert result.status_code == status, result.text
        assert body['new_password'] not in result.text
    assert client.get('/api/v1/auth/me').status_code == 200
    assert client.post('/api/v1/auth/login', json={'email': doctor['email'], 'password': OLD}).status_code == 200


def test_eds_account_can_set_password_without_knowing_random_initial_password(client, doctor):
    from app.security import passwords
    with DbSession(engine) as db:
        stored = db.get(Doctor, doctor['id'])
        stored.profile = {**stored.profile, 'method': 'sigex', 'email': '', 'iin_verified': True}
        stored.login_hash = digest('eds:' + doctor['iin'])
        stored.password_hash = passwords.hash('Synthetic-random-initial-password-unknown-to-user')
        db.commit()
    assert client.patch('/api/v1/auth/profile', json={'email': 'eds@example.test', 'phone': ''}).status_code == 200
    assert client.post('/api/v1/auth/password', json=password_body()).status_code == 200
    assert client.post('/api/v1/auth/logout').status_code == 200
    signed_in = client.post('/api/v1/auth/login', json={'email': 'eds@example.test', 'password': NEW})
    assert signed_in.status_code == 200 and signed_in.json()['id'] == doctor['id']
    assert signed_in.json()['iin_verified'] is True
