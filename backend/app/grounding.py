"""Клинические факты модели принимаются как цитаты, не как непроверяемый пересказ."""
import hashlib
import json
from .clinical import DOCUMENT_FIELDS

PHYSICIAN_DECISIONS = {'diagnosis', 'diagnosis_code', 'recommendations', 'follow_up'}


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
                if '?' not in full and '[ПЕРСОНАЛЬНЫЕ ДАННЫЕ]' not in quote.text:
                    # Сохраняем целую реплику: вырезанная моделью цитата может потерять отрицание.
                    valid.append({'segment': quote.segment, 'text': full})
        if valid:
            sources[source.field] = {'field': source.field, 'segments': sorted({q['segment'] for q in valid}),
                                    'quotes': valid, 'revision': transcript_revision(segments)}
    for field in DOCUMENT_FIELDS - {'visit_type', 'visit_format'}:
        if not result[field]:
            continue
        if field in PHYSICIAN_DECISIONS or field not in sources:
            result[field] = ''
            warnings.append(f'{field}: вывод модели не внесён в лист; требуется решение врача или точный источник.')
            sources.pop(field, None)
        else:
            result[field] = '\n\n'.join(dict.fromkeys(q['text'] for q in sources[field]['quotes']))
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
