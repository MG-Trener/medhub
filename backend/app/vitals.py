"""Консервативное извлечение измерений из цитат RU/KK без медицинских выводов."""
import re

WORDS = {
    'ноль':0, 'один':1, 'одна':1, 'два':2, 'две':2, 'три':3, 'четыре':4, 'пять':5, 'шесть':6,
    'семь':7, 'восемь':8, 'девять':9, 'десять':10, 'одиннадцать':11, 'двенадцать':12,
    'тринадцать':13, 'четырнадцать':14, 'пятнадцать':15, 'шестнадцать':16, 'семнадцать':17,
    'восемнадцать':18, 'девятнадцать':19, 'двадцать':20, 'тридцать':30, 'сорок':40,
    'пятьдесят':50, 'шестьдесят':60, 'семьдесят':70, 'восемьдесят':80, 'девяносто':90,
    'сто':100, 'двести':200, 'триста':300,
    'нөл':0, 'бір':1, 'екі':2, 'үш':3, 'төрт':4, 'бес':5, 'алты':6, 'жеті':7, 'сегіз':8,
    'тоғыз':9, 'он':10, 'жиырма':20, 'отыз':30, 'қырық':40, 'елу':50, 'алпыс':60,
    'жетпіс':70, 'сексен':80, 'тоқсан':90, 'жүз':100,
}
LABELS = {
    'temperature': r'температур[аы]|дене қызуы',
    'pulse': r'пульс|жүрек соғу жиілігі|тамыр соғысы',
    'blood_pressure': r'давление|ад|қан қысымы|қан қысымым',
    'spo2': r'spo2|сатурация', 'height': r'рост|бойым|бойы', 'weight': r'вес|салмағым|салмағы',
    'respiratory_rate': r'чдд|частота дыхания|тыныс алу жиілігі',
}


def numeric_words(value):
    words = value.casefold().split()
    if not words or any(word not in WORDS for word in words):
        return ''
    # Только нисходящие разряды. «Один два три» — перечисление, не 6.
    values = [WORDS[w] for w in words]
    if any(left <= right for left, right in zip(values, values[1:])):
        return ''
    return str(sum(values))


def extract_vital(field, quotes):
    number = r'\d{1,3}(?:[.,]\d{1,2})?'
    spoken = '(?:' + '|'.join(sorted(WORDS, key=len, reverse=True)) + ')'
    value = rf'(?:{number}|{spoken}(?:\s+{spoken}){{0,2}})'
    pattern = rf'(?<!\w)(?:{LABELS[field]})(?!\w)\s*(?:составляет|равен|равна|измерена)?\s*[:—-]?\s*({value})'
    if field == 'blood_pressure':
        pattern += rf'\s*(?:/|на|-ке|ге|ден)\s*({value})'
    measurements = []
    for text in quotes:
        for match in re.finditer(pattern, text, re.I):
            values = [v.replace(',', '.') if re.fullmatch(number, v) else numeric_words(v) for v in match.groups()]
            if all(values):
                measurements.append('/'.join(values))
    # Не выбираем одно из противоречащих измерений по догадке.
    values = list(dict.fromkeys(measurements))
    return values[0] if len(values) == 1 else ''
