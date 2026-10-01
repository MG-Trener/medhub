import json
import httpx
import pytest
from pydantic import ValidationError
from app.config import settings
from app.providers import generate


@pytest.mark.parametrize('provider,response_format', [('ollama', 'json_object'), ('openai_compatible', 'json_object'), ('openai_compatible', 'json_schema')])
def test_provider_returns_separate_ai_conclusion(monkeypatch, provider, response_format):
    monkeypatch.setattr(settings(), 'llm_provider', provider)
    monkeypatch.setattr(settings(), 'llm_response_format', response_format)
    monkeypatch.setattr(settings(), 'llm_api_key', '')
    monkeypatch.setattr(settings(), 'llm_url', 'http://127.0.0.1:11434')
    content = json.dumps({'fields': {'anamnesis': 'Сведения со слов пациента.',
        'ai_test_recommendations': 'Данных недостаточно; анамнез требует уточнения.', 'ai_diagnosis_variants': 'Недостаточно данных.'}})

    def post(self, url, **kwargs):
        if provider == 'openai_compatible':
            assert 'Authorization' not in kwargs['headers']
            assert kwargs['json']['response_format']['type'] == response_format
            if response_format == 'json_schema':
                schema = kwargs['json']['response_format']['json_schema']['schema']
                assert {'ai_test_recommendations', 'ai_diagnosis_variants'} <= set(schema['$defs']['GeneratedConsultation']['required'])
        prompt = kwargs['json']['messages'][0]['content']
        assert 'Это не диагноз' in prompt
        assert 'ai_test_recommendations' in prompt and 'ai_diagnosis_variants' in prompt
        body = {'message': {'content': content}} if provider == 'ollama' else {'choices': [{'message': {'content': content}}]}
        return httpx.Response(200, request=httpx.Request('POST', url), json=body)

    monkeypatch.setattr(httpx.Client, 'post', post)
    result = generate([{'speaker': 'SPEAKER_00', 'text': 'Сведения со слов пациента.'}])
    assert result['fields']['diagnosis'] == ''
    assert result['fields']['ai_test_recommendations'] == 'Данных недостаточно; анамнез требует уточнения.'
    # Ответ без заключения не выдаётся за успешно сформированный результат.
    content = json.dumps({'fields': {'anamnesis': 'Текст'}})
    with pytest.raises(ValidationError):
        generate([])


@pytest.mark.parametrize('configured', [False, True])
def test_optional_local_inference_controls_and_credentials(monkeypatch, configured):
    s = settings()
    monkeypatch.setattr(s, 'llm_provider', 'openai_compatible')
    monkeypatch.setattr(s, 'llm_url', 'http://127.0.0.1:1234/v1')
    monkeypatch.setattr(s, 'llm_api_key', 'synthetic-token' if configured else '')
    monkeypatch.setattr(s, 'llm_reasoning_effort', 'none' if configured else '')
    monkeypatch.setattr(s, 'llm_max_tokens', 2048 if configured else 0)
    monkeypatch.setattr(s, 'llm_temperature', 0.1 if configured else None)

    def post(self, url, **kwargs):
        payload = kwargs['json']
        for key, value in [('reasoning_effort', 'none'), ('max_tokens', 2048), ('temperature', 0.1)]:
            if configured:
                assert payload[key] == value
            else:
                assert key not in payload
        assert kwargs['headers'] == ({'Authorization': 'Bearer synthetic-token'} if configured else {})
        assert json.loads(payload['messages'][1]['content'])['current_fields']['anamnesis'] == 'Правка врача'
        content = json.dumps({'fields': {'ai_test_recommendations': 'Недостаточно данных.',
                                        'ai_diagnosis_variants': 'Недостаточно данных.'}})
        return httpx.Response(200, request=httpx.Request('POST', url),
                              json={'choices': [{'message': {'content': content}}]})

    monkeypatch.setattr(httpx.Client, 'post', post)
    generate([], {'anamnesis': 'Правка врача'})


def test_compact_local_facts_are_grounded_and_normalized(monkeypatch):
    s = settings()
    monkeypatch.setattr(s, 'llm_provider', 'openai_compatible')
    monkeypatch.setattr(s, 'llm_url', 'http://127.0.0.1:1234/v1')
    monkeypatch.setattr(s, 'llm_response_format', 'json_schema')
    monkeypatch.setattr(s, 'llm_compact_extraction', True)
    transcript = [{'speaker': 'SPEAKER_00', 'text': 'Аллергии на пенициллин нет. Пульс семьдесят два.'}]
    content = json.dumps({'facts': [
        {'field': 'allergies', 'quotes': [{'segment': 0, 'text': 'пенициллин'}]},
        {'field': 'pulse', 'quotes': [{'segment': 0, 'text': 'Пульс семьдесят два.'}]},
        {'field': 'complaints', 'quotes': [{'segment': 0, 'text': 'Выдуманная жалоба'}]}],
        'speaker_roles': [{'speaker': 'SPEAKER_00', 'role': 'patient'}], 'ai_questions': [],
        'ai_test_recommendations': 'Сначала осмотр.', 'ai_diagnosis_variants': 'Данных недостаточно.', 'warnings': []})
    def post(self, url, **kwargs):
        schema = kwargs['json']['response_format']['json_schema']['schema']
        assert 'facts' in schema['properties'] and 'fields' not in schema['properties']
        return httpx.Response(200, request=httpx.Request('POST', url),
            json={'choices': [{'message': {'content': content}}]})
    monkeypatch.setattr(httpx.Client, 'post', post)
    result = generate(transcript, target='live')
    assert result['fields']['allergies'] == 'Аллергии на пенициллин нет.'
    assert result['fields']['pulse'] == '72' and result['fields']['complaints'] == ''
    assert result['fields']['diagnosis'] == ''
    assert result['speaker_roles'] == {'SPEAKER_00': 'patient'}
    assert result['fields']['ai_test_recommendations'] == ''
