from datetime import date
import pytest
from pydantic import ValidationError
from app.schemas import PatientInput, Register, IdentityStart
from app.patient_input import birth_date_from_iin


def test_masks_are_normalized_and_birth_date_is_inferred():
    p = PatientInput(name='Синтетический пациент', iin='900101 300001', phone='+7 (701) 123-45-67')
    assert p.iin == '900101300001'
    assert p.birth_date == date(1990, 1, 1)
    assert p.phone == '+77011234567'
    assert PatientInput(name=p.name, iin=p.iin, phone='87011234567').phone == p.phone
    assert IdentityStart(purpose='register', iin='900101 300001').iin == p.iin
    assert Register(name='Врач', iin='900101 300001', email='synthetic@example.test', password='synthetic-password').iin == p.iin


def test_document_birth_date_has_priority_and_non_date_iin_is_allowed():
    assert PatientInput(name='Тест', iin='900101300001', birth_date='1991-02-03').birth_date == date(1991, 2, 3)
    assert PatientInput(name='Тест', iin='000000009900', birth_date='1991-02-03').birth_date == date(1991, 2, 3)
    assert birth_date_from_iin('000229600001') == date(2000, 2, 29)
    for value in ['010229500001', '990101500001', '900101900001', '900132300001', '900101']:
        assert birth_date_from_iin(value) is None
    with pytest.raises(ValidationError):
        PatientInput(name='Тест', iin='000000009900')


@pytest.mark.parametrize('phone', ['+7 (701) 12', 'abc7011234567', '+17011234567'])
def test_incomplete_or_invalid_phones_are_rejected(phone):
    with pytest.raises(ValidationError):
        PatientInput(name='Тест', iin='900101300001', phone=phone)


def test_patient_api_accepts_masks_and_searches_formatted_iin(client, doctor):
    created = client.post('/api/v1/patients', json={'name': 'Синтетический пациент',
        'iin': '900101 300001', 'phone': '+7 (701) 123-45-67'})
    assert created.status_code == 201
    patient = created.json()
    assert patient['iin'] == '900101300001' and patient['birth_date'] == '1990-01-01'
    assert patient['phone'] == '+77011234567'
    assert client.get('/api/v1/patients', params={'q': '900101 300001'}).json()[0]['id'] == patient['id']
