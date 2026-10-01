import pytest
from app.vitals import extract_vital


@pytest.mark.parametrize('field,text,value', [
    ('pulse', 'Измерила пульс семьдесят два.', '72'),
    ('blood_pressure', 'Давление сто двадцать на восемьдесят, пульс 72.', '120/80'),
    ('blood_pressure', 'Қан қысымы 120/80.', '120/80'),
    ('temperature', 'Температура 38,2 градуса.', '38.2'),
    ('pulse', 'Пульс жетпіс екі.', '72'),
    ('weight', 'Салмағым 70 кг.', '70'),
])
def test_ru_kk_vitals(field, text, value):
    assert extract_vital(field, [text]) == value


def test_no_guessing_on_conflict_or_unrelated_numbers():
    assert extract_vital('pulse', ['Возраст 72, пульс не измеряли.']) == ''
    assert extract_vital('pulse', ['Пульс 72.', 'Пульс 100.']) == ''
