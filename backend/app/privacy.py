"""Маскирование целого диалога с проекцией совпадений обратно на реплики."""
import re

MASK = '[ПЕРСОНАЛЬНЫЕ ДАННЫЕ]'
PATTERNS = (
    r'(?<!\d)(?:\d[\s-]*){12}(?!\d)',
    r'(?<!\d)(?:\+?7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)',
    r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}',
    r'(?:меня зовут|мо[её] имя|фамилия|менің атым|аты-ж[өо]нім|есімім)\s*[:—-]?\s*[^.!?,;\n]+',
    r'(?:живу по адресу|проживаю|адрес|мекенжайым|мекенжай|тұратын жерім)\s*[:—-]?\s*[^.!?;\n]+',
    r'(?:дата рождения|родил[а-я]*|туған күнім|туған күн[іi])\s*[:—-]?\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}',
    r'(?:паспорт|удостоверение|номер карты|номер полиса|құжат нөмірі)\s*[:№—-]?\s*[\w-]{4,80}',
    r'https?://\S+|(?<!\w)@[\w.]{3,}',
)


def sensitive_spans(text, patient=None):
    patient = patient or {}
    patterns = list(PATTERNS)
    values = [patient.get(key, '') for key in ('iin', 'phone', 'birth_date', 'email', 'address')]
    values += re.findall(r'[\w-]{3,}', patient.get('name', ''))
    for value in filter(None, values):
        patterns.append(r'(?<!\w)' + re.escape(str(value)) + r'(?!\w)')
    spans = sorted((match.start(), match.end()) for pattern in patterns
                   for match in re.finditer(pattern, text, re.I))
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def redact(text, patient=None):
    for start, end in reversed(sensitive_spans(text, patient)):
        text = text[:start] + MASK + text[end:]
    return text


def redact_segments(segments, patient=None):
    joined = ' '.join(s['text'] for s in segments)
    spans = sensitive_spans(joined, patient)
    offset, result = 0, []
    for segment in segments:
        value, size = segment['text'], len(segment['text'])
        overlaps = [(max(0, start - offset), min(size, end - offset))
                    for start, end in spans if start < offset + size and end > offset]
        for start, end in reversed(overlaps):
            value = value[:start] + MASK + value[end:]
        result.append({**segment, 'text': value})
        offset += size + 1
    return result


def redact_clinical_context(fields, patient=None):
    from .clinical import DOCUMENT_FIELDS, AI_FIELDS

    def mask(value):
        if isinstance(value, str):
            return redact(value, patient)
        if isinstance(value, list):
            return [mask(item) for item in value]
        if isinstance(value, dict):
            return {key: mask(item) for key, item in value.items()}
        return value

    return {key: mask(value) for key, value in fields.items() if key in DOCUMENT_FIELDS | AI_FIELDS}
