from app.grounding import grounded_fields, transcript_revision
from app.schemas import Consultation
from app.clinical import merge_generated_fields


def test_quotes_preserve_negation_and_reject_unfounded_decisions():
    segments = [{'speaker': 'SPEAKER_00', 'start': 0, 'end': 3, 'text': 'Аллергии на пенициллин нет.'}]
    fields = Consultation(allergies='Аллергия на пенициллин', diagnosis='Астма', recommendations='Принимать антибиотик',
        sources=[{'field': 'allergies', 'segments': [0], 'quotes': [{'segment': 0, 'text': 'пенициллин'}]}])
    result = grounded_fields(fields, segments)
    assert result['allergies'] == segments[0]['text']
    assert result['diagnosis'] == result['recommendations'] == ''
    assert result['sources'][0]['revision'] == transcript_revision(segments)


def test_invalid_quote_question_and_unsupported_value_are_removed():
    segments = [{'text': 'Болит голова?'}]
    fields = Consultation(complaints='Болит голова', anamnesis='Три дня',
        sources=[{'field': 'complaints', 'segments': [0], 'quotes': [{'segment': 0, 'text': 'Болит голова'}]},
                 {'field': 'anamnesis', 'segments': [0], 'quotes': [{'segment': 0, 'text': 'Три дня'}]}])
    result = grounded_fields(fields, segments)
    assert result['complaints'] == result['anamnesis'] == '' and result['sources'] == []


def test_manual_lock_survives_model_generated_lock_list():
    result = merge_generated_fields({'allergies': 'Пенициллин', 'locked_fields': ['allergies']},
                                    {'allergies': 'Нет аллергий', 'locked_fields': []})
    assert result['allergies'] == 'Пенициллин' and result['locked_fields'] == ['allergies']


def test_quote_context_preserves_negation_without_other_topics():
    segments = [{'text': 'Аллергии на пенициллин нет. Принимаю аспирин. Осмотр ещё не выполнен.'}]
    fields = Consultation(allergies='Пенициллин', medications='Аспирин', examination='Осмотр', sources=[
        {'field': 'allergies', 'quotes': [{'segment': 0, 'text': 'пенициллин'}]},
        {'field': 'medications', 'quotes': [{'segment': 0, 'text': 'аспирин'}]},
        {'field': 'examination', 'quotes': [{'segment': 0, 'text': 'Осмотр ещё не выполнен.'}]}])
    result = grounded_fields(fields, segments)
    assert result['allergies'] == 'Аллергии на пенициллин нет.'
    assert result['medications'] == 'Принимаю аспирин.'
    assert result['examination'] == ''


def test_exact_sources_fill_empty_fields_and_spoken_vitals():
    segments = [{'text': 'Басым үш күннен бері ауырады. Жүрегім айнымайды.'},
                {'text': 'Давление сто двадцать на восемьдесят, пульс семьдесят два.'}]
    fields = Consultation(sources=[
        {'field': 'complaints', 'quotes': [{'segment': 0, 'text': segments[0]['text']}]},
        {'field': 'blood_pressure', 'quotes': [{'segment': 1, 'text': segments[1]['text']}]},
        {'field': 'pulse', 'quotes': [{'segment': 1, 'text': segments[1]['text']}]}])
    result = grounded_fields(fields, segments)
    assert result['complaints'] == segments[0]['text']
    assert result['blood_pressure'] == '120/80' and result['pulse'] == '72'


def test_lock_requires_explicit_unlock_and_current_version(client, doctor):
    from test_workflow import patient, encounter
    e = encounter(client, patient(client))
    assert 'complaints' in e['fields']['locked_fields']
    r = client.post(f'/api/v1/encounters/{e["id"]}/field-lock', json={'version': e['version'], 'field': 'complaints', 'locked': False})
    assert r.status_code == 200 and 'complaints' not in r.json()['fields']['locked_fields']
    assert client.post(f'/api/v1/encounters/{e["id"]}/field-lock', json={'version': e['version'], 'field': 'complaints', 'locked': True}).status_code == 409
