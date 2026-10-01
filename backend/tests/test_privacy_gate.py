import pytest
from app.config import settings
from app.privacy_gate import prepare_ai_input, local_private_text
from app.providers import ProviderError


def test_external_model_fails_closed_without_local_detector(monkeypatch):
    monkeypatch.setattr(settings(), 'llm_provider', 'openai')
    monkeypatch.setattr(settings(), 'privacy_service_url', '')
    monkeypatch.setattr(settings(), 'privacy_ner_model', '')
    with pytest.raises(ProviderError):
        prepare_ai_input([{'text': 'Айгүл пришла с жалобой.'}], {'anamnesis': 'Частные данные'})


def test_local_detector_covers_long_text_and_keeps_clinical_details(monkeypatch):
    local_private_text.cache_clear()
    class Detector:
        def predict_entities(self, text, labels, threshold):
            a = text.find('Айгүл')
            return [] if a == -1 else [{'start': a, 'end': a + 5}]
    monkeypatch.setattr('app.privacy_gate.ner', lambda: Detector())
    value = 'Симптомы без имени. ' * 120 + 'Айгүл, 28 лет, женщина. Аллергия жоқ, 500 мг.'
    safe = local_private_text(value)
    assert 'Айгүл' not in safe
    assert '28 лет, женщина' in safe and 'Аллергия жоқ, 500 мг' in safe
    local_private_text.cache_clear()


def test_context_and_cross_segment_name_are_protected(monkeypatch):
    monkeypatch.setattr(settings(), 'llm_provider', 'openai')
    monkeypatch.setattr(settings(), 'privacy_service_url', '')
    monkeypatch.setattr(settings(), 'privacy_ner_model', 'synthetic-local-model')
    monkeypatch.setattr('app.privacy_gate.local_private_text', lambda t: t.replace('Айгүл Садыкова', '[ПЕРСОНАЛЬНЫЕ ДАННЫЕ]').replace('Айгүл', '[ПЕРСОНАЛЬНЫЕ ДАННЫЕ]'))
    safe, context = prepare_ai_input([{'text': 'Айгүл'}, {'text': 'Садыкова. Аллергия жоқ.'}],
                                     {'anamnesis': 'Айгүл. 28 лет', 'ai_questions': ['Айгүл?']})
    assert 'Айгүл' not in str(safe) + str(context) and 'Садыкова' not in str(safe)
    assert '28 лет' in context['anamnesis']
