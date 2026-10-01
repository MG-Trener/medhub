"""Синтетический smoke-корпус: не заменяет клиническую и multilingual NER-приёмку."""
import argparse
import os
import time
import httpx

CASES = [
    ('Меня зовут Алия Садыкова. Мне 28 лет, женщина. Аллергии нет.', ['Алия', 'Садыкова'], ['28 лет', 'женщина', 'Аллергии нет']),
    ('Менің атым Айгүл. Жасым 32-де. Аллергия жоқ, парацетамол 500 мг.', ['Айгүл'], ['32', 'Аллергия жоқ', '500 мг']),
    ('ИИН 991231 123456. Боль с 01.10.2026, температура 38.2.', ['991231', '123456'], ['01.10.2026', '38.2']),
    ('Телефон +7 701 123 45 67. Половая жизнь с 18 лет, 2 партнёра.', ['701', '123 45 67'], ['18 лет', '2 партнёра']),
    ('Почта patient@example.test. Принимаю амоксициллин 500 мг 3 раза в день.', ['patient@example.test'], ['500 мг', '3 раза']),
    ('Айгүл Садыкова пришла с жалобой на боль. Ей 35 лет.', ['Айгүл', 'Садыкова'], ['35 лет']),
    ('Мекенжайым Астана, Абая 10. Қан қысымым 120/80.', ['Астана', 'Абая'], ['120/80']),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--token-env', default='ASR_SERVICE_TOKEN')
    args = parser.parse_args()
    from urllib.parse import urlsplit
    import ipaddress
    host = urlsplit(args.url).hostname or ''
    try:
        valid = ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_private
    except ValueError:
        valid = host == 'localhost'
    if not valid:
        raise SystemExit('Use a private/loopback address for this synthetic evaluation')
    token = os.environ.get(args.token_env, '')
    if len(token) < 32:
        raise SystemExit('Set token in the named environment variable; do not pass it in arguments')
    started = time.monotonic()
    response = httpx.post(args.url.rstrip('/') + '/redact', json={'texts': [x[0] for x in CASES]},
                          headers={'Authorization': 'Bearer ' + token}, timeout=180)
    response.raise_for_status()
    results = response.json()['texts']
    if len(results) != len(CASES):
        raise SystemExit('Invalid result count')
    failures = 0
    for index, ((_, secrets, clinical), safe) in enumerate(zip(CASES, results), 1):
        leak = any(secret in safe for secret in secrets)
        lost = any(fact not in safe for fact in clinical)
        failures += int(leak or lost)
        print(f'Case {index}: leak={leak}, clinical_loss={lost}')
    print(f'{len(CASES)} synthetic cases, failures={failures}, elapsed={time.monotonic() - started:.1f}s')
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
