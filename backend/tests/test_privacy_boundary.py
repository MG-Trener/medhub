import pytest
from app.privacy import redact, redact_segments
from app.ai_policy import trusted_url, require_trusted_asr, llm_is_external
from app.config import settings
from app.providers import transcribe, ProviderError
from app.openai_asr import transcribe_openai


def test_split_identifiers_and_preserved_history():
    text = ['ИИН 991231', '123456. Мне 26 лет, женщина.', 'Менің атым Айгүл. Аллергия жоқ. Принимаю 500 мг.', '+7 701', '123 45 67']
    segments = [{'text': x, 'start': i, 'end': i + 1, 'speaker': 'SPEAKER_00'} for i, x in enumerate(text)]
    masked = redact_segments(segments)
    joined = ' '.join(x['text'] for x in masked)
    for secret in ('991231', '123456', 'Айгүл', '701', '123 45 67'):
        assert secret not in joined
    for clinical in ('26 лет', 'женщина', 'Аллергия жоқ', '500 мг'):
        assert clinical in joined
    assert [(s['start'], s['end']) for s in masked] == [(s['start'], s['end']) for s in segments]


def test_clinical_dates_and_sexual_history_are_retained():
    text = 'Температура 38.2, болею с 01.10.2026, половая жизнь с 18 лет, 2 партнёра.'
    assert redact(text) == text
    assert '01.01.2000' not in redact('Дата рождения 01.01.2000. Боль с 01.10.2026.')


@pytest.mark.parametrize('url', ['http://172.example.test', 'http://172.200.1.1', 'https://api.example.test', 'http://localhost.attacker.test', 'http://user:pass@localhost'])
def test_untrusted_endpoint(url):
    assert not trusted_url(url)


@pytest.mark.parametrize('url', ['http://127.0.0.1:8090', 'http://10.9.0.3:8090', 'http://172.16.1.1', 'http://[::1]:8090'])
def test_trusted_endpoint(url):
    assert trusted_url(url)


def test_raw_external_asr_never_calls_network(monkeypatch):
    settings().asr_provider = 'openai'
    with pytest.raises(ProviderError):
        transcribe('unused.audio')
    with pytest.raises(ProviderError):
        transcribe_openai('unused.audio')


def test_openai_always_external(monkeypatch):
    monkeypatch.setattr(settings(), 'llm_provider', 'openai')
    settings().llm_is_cloud = False
    assert llm_is_external()


def test_consent_never_bypasses_cloud_review(client, doctor, monkeypatch):
    from test_workflow import patient, encounter
    p = patient(client)
    client.patch(f'/api/v1/patients/{p["id"]}/consent', json={'processing_consent': True})
    e = encounter(client, p)
    monkeypatch.setattr(settings(), 'llm_provider', 'openai')
    assert client.post(f'/api/v1/encounters/{e["id"]}/generate', json={'version': e['version']}).status_code == 403
    reviewed = client.post(f'/api/v1/encounters/{e["id"]}/privacy-review', json={'version': e['version'], 'segments': []}).json()
    assert client.post(f'/api/v1/encounters/{e["id"]}/generate', json={'version': reviewed['version']}).status_code == 202
