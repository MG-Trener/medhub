"""Расшифровать локальную копию архива без БД и внешних API.

Пример: python scripts/decrypt_audio.py --env-file .env.production
  --input data/audio-encrypted --output data/audio-decrypted
Зависимости: cryptography, python-dotenv (есть в окружении backend).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import dotenv_values


def extension(data):
    if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
        return '.wav'
    if data.startswith(b'\x1a\x45\xdf\xa3'):
        return '.webm'
    if data.startswith(b'OggS'):
        return '.ogg'
    if data.startswith(b'fLaC'):
        return '.flac'
    if data[4:8] == b'ftyp':
        return '.mp4'
    if data.startswith(b'ID3') or (len(data) > 1 and data[0] == 255 and data[1] & 0xe0 == 0xe0):
        return '.mp3'
    return '.bin'


def export_archive(source, destination, key):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir():
        raise ValueError('Каталог исходного архива не найден')
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Исходный каталог и результат должны быть отдельными папками')
    cipher = Fernet(key)
    files = sorted(source.rglob('*.enc'))
    if not files:
        raise ValueError('В архиве нет файлов .enc')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    results = []
    for path in files:
        entry = {'source': path.relative_to(source).as_posix()}
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(source):
                raise ValueError('Ссылка за пределы архива')
            data = cipher.decrypt(path.read_bytes())
            target = destination / path.relative_to(source).with_suffix(extension(data))
            if not target.resolve().is_relative_to(destination) or target.is_symlink():
                raise ValueError('Небезопасный путь результата')
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            digest = hashlib.sha256(data).hexdigest()
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    raise ValueError('Готовый файл отличается; перезапись запрещена')
                status = 'already_exported'
            else:
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    with os.fdopen(fd, 'wb') as output:
                        output.write(data)
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise
                status = 'exported'
            entry.update(status=status, output=target.relative_to(destination).as_posix(),
                         bytes=len(data), sha256=digest)
        except InvalidToken:
            entry.update(status='error', error='Неверный ключ или повреждённый файл')
        except (OSError, ValueError) as exc:
            entry.update(status='error', error=type(exc).__name__)
        results.append(entry)
    # Отчёт хранится рядом с аудио, в закрытом каталоге, и не содержит ключа.
    report = destination / 'manifest.json'
    if report.is_symlink():
        raise ValueError('Отчёт не должен быть символической ссылкой')
    fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(results, output, ensure_ascii=False, indent=2)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, help='Файл с ENCRYPTION_KEY; ключ не передаётся аргументом')
    parser.add_argument('--input', required=True, type=Path, help='Локальная копия каталога с .enc')
    parser.add_argument('--output', required=True, type=Path, help='Отдельная папка для расшифрованных файлов')
    args = parser.parse_args()
    if args.env_file and not args.env_file.is_file():
        parser.error('Файл конфигурации не найден')
    values = dotenv_values(args.env_file) if args.env_file else os.environ
    key = values.get('ENCRYPTION_KEY')
    if not key:
        parser.error('ENCRYPTION_KEY отсутствует в конфигурации')
    try:
        results = export_archive(args.input, args.output, key.encode())
    except (OSError, ValueError):
        parser.exit(1, 'Не удалось открыть архив/результат или настроить ключ. Проверьте пути и конфигурацию.\n')
    counts = {status: sum(r['status'] == status for r in results)
              for status in ('exported', 'already_exported', 'error')}
    print(json.dumps(counts))
    return int(bool(counts['error']))


if __name__ == '__main__':
    raise SystemExit(main())
