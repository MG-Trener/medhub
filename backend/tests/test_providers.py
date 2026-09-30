import json
import httpx
import pytest
from pydantic import ValidationError
from app.config import settings
from app.providers import generate


@pytest.mark.parametrize('provider', ['ollama', 'openai_compatible'])
def test_provider_returns_separate_ai_conclusion(monkeypatch, provider):
    monkeypatch.setattr(settings(), 'llm_provider', provider)
    monkeypatch.setattr(settings(), 'llm_url', 'http://model.example.test')
    content = json.dumps({'fields': {'anamnesis': 'Сведения со слов пациента.',
        'ai_test_recommendations': 'Данных недостаточно; анамнез требует уточнения.', 'ai_diagnosis_variants': 'Недостаточно данных.'}})

    def post(self, url, **kwargs):
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
