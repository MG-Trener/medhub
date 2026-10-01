"""Клинические факты модели принимаются как цитаты, не как непроверяемый пересказ."""
import hashlib
import json
import re
from .clinical import DOCUMENT_FIELDS

PHYSICIAN_DECISIONS = {'diagnosis', 'diagnosis_code', 'recommendations', 'follow_up'}


def sentence_context(full, quote):
    """Расширяем цитату до предложений, сохраняя отрицание без соседних тем."""
    start = full.find(quote.strip())
    end = start + len(quote.strip())
    boundaries = [0, *[m.end() for m in re.finditer(r'(?<!\d)[.!?;](?!\d)|\n', full)], len(full)]
    left = max(b for b in boundaries if b <= start)
    right = min(b for b in boundaries if b >= end)
    return full[left:right].strip()


def transcript_revision(segments):
    return hashlib.sha256(json.dumps(segments, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def grounded_fields(fields, segments):
    result = fields.model_dump()
    sources, warnings = {}, list(result['warnings'])
    for source in fields.sources:
        if source.field not in DOCUMENT_FIELDS or not source.quotes:
            continue
        valid = []
        for quote in source.quotes:
            if quote.segment < len(segments) and quote.text.strip() in segments[quote.segment]['text']:
                # Вопрос/вырезанные ПДн не превращаются в положительное утверждение.
                full = segments[quote.segment]['text'].strip()
                context = sentence_context(full, quote.text)
                if '?' not in context and '[ПЕРСОНАЛЬНЫЕ ДАННЫЕ]' not in context:
                    if source.field == 'examination' and re.search(
                        r'осмотр.{0,25}(не выполн|не провед|ещ[её] не)|осмотр.{0,15}(позже|после)|'
                        r'қарау.{0,20}(жүргізілген жоқ|жүргізілмеген)', context, re.I):
                        continue
                    valid.append({'segment': quote.segment, 'text': context})
        if valid:
            sources[source.field] = {'field': source.field, 'segments': sorted({q['segment'] for q in valid}),
                                    'quotes': valid, 'revision': transcript_revision(segments)}
    for field in DOCUMENT_FIELDS - {'visit_type', 'visit_format'}:
        if not result[field] and field not in sources:
            continue
        if field in PHYSICIAN_DECISIONS or field not in sources:
            populated = bool(result[field])
            result[field] = ''
            if populated:
                warnings.append(f'{field}: вывод модели не внесён в лист; требуется решение врача или точный источник.')
            sources.pop(field, None)
        else:
            quotes = list(dict.fromkeys(q['text'] for q in sources[field]['quotes']))
            from .vitals import LABELS, extract_vital
            result[field] = extract_vital(field, quotes) if field in LABELS else '\n\n'.join(quotes)
            if not result[field]:
                sources.pop(field, None)
                warnings.append(f'{field}: измерение неоднозначно; проверьте исходную реплику.')
            # Ограничение схемы действует и после расширения цитаты до целой реплики.
            maximum = next(m.max_length for m in type(fields).model_fields[field].metadata if hasattr(m, 'max_length'))
            if len(result[field]) > maximum:
                result[field] = ''
                sources.pop(field, None)
                warnings.append(f'{field}: цитата слишком длинная, перенесите измерение вручную.')
    result['sources'] = list(sources.values())
    result['warnings'] = list(dict.fromkeys(warnings))[:20]
    result['reviewed_fields'], result['locked_fields'] = [], []
    return result


def manual_fields(previous, incoming):
    result = incoming.model_dump()
    locked = set(previous.get('locked_fields', []))
    changed = {k for k in DOCUMENT_FIELDS if result.get(k) != previous.get(k, '')
               and k not in ('visit_type', 'visit_format')}
    locked.update(changed)
    result['locked_fields'] = sorted(locked & DOCUMENT_FIELDS)
    result['sources'] = [s for s in result['sources'] if s['field'] not in changed]
    result['reviewed_fields'] = [k for k in result['reviewed_fields'] if k in DOCUMENT_FIELDS]
    return result
