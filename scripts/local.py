"""Локальный MedHub без Docker: .venv/Scripts/python.exe scripts/local.py."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

import psycopg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'local'
PORT = 55432


def available(port):
    with socket.socket() as sock:
        return sock.connect_ex(('127.0.0.1', port)) != 0


def wait_http(url, processes):
    for _ in range(60):
        if any(p.poll() is not None for p in processes):
            raise RuntimeError('Сервис остановился; проверьте журналы в data/local.')
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError('Сервис не ответил за 60 секунд; проверьте data/local.')


def main():
    values = dotenv_values(ROOT / '.env')
    if not values:
        raise RuntimeError('Сначала заполните .env в корне проекта.')
    url = make_url(values.get('DATABASE_URL', ''))
    if url.database != 'medhub' or not url.drivername.startswith('postgresql'):
        raise RuntimeError('Для локального запуска требуется отдельная БД medhub.')
    node = shutil.which('node')
    vite = ROOT / 'frontend' / 'node_modules' / 'vite' / 'bin' / 'vite.js'
    if not node or not vite.exists():
        raise RuntimeError('Установите Node.js и зависимости frontend: pnpm install --frozen-lockfile.')
    for port in (8010, 5173):
        if not available(port):
            raise RuntimeError(f'Порт {port} уже занят. Остановите предыдущий запуск.')
    env = {**os.environ, **{k: v for k, v in values.items() if v is not None}}
    env.update(PUBLIC_ORIGIN='http://localhost:5173', SECURE_COOKIES='false',
               AUDIO_DIR=str(DATA / 'audio'))
    DATA.mkdir(parents=True, exist_ok=True)
    pg_ctl = None
    pg_started = False
    processes = []
    logs = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        # Адрес db принадлежит Compose. Для него используем собственный кластер,
        # не меняя системный PostgreSQL, исходный .env и его базу postgres.
        if url.host == 'db':
            candidates = sorted(Path('C:/Program Files/PostgreSQL').glob('*/bin/pg_ctl.exe'),
                                key=lambda p: int(p.parents[1].name), reverse=True)
            if not candidates:
                raise RuntimeError('Установите PostgreSQL для запуска без Docker.')
            pg_ctl = candidates[0]
            cluster = DATA / 'postgres'
            if not (cluster / 'PG_VERSION').exists():
                if cluster.exists() and any(cluster.iterdir()):
                    raise RuntimeError('Кластер не инициализирован; проверьте data/local/postgres.')
                if not url.username or not url.password:
                    raise RuntimeError('В DATABASE_URL нужны пользователь и пароль.')
                # Временный файл пароля удаляется сразу после initdb.
                fd, password_file = tempfile.mkstemp(dir=DATA, suffix='.secret')
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                        handle.write(url.password + '\n')
                    subprocess.run([str(pg_ctl.with_name('initdb.exe')), '-D', str(cluster),
                                    '-U', url.username, '--pwfile', password_file,
                                    '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C'],
                                   check=True, creationflags=flags)
                finally:
                    Path(password_file).unlink(missing_ok=True)
            url = url.set(host='127.0.0.1', port=PORT)
            if available(PORT):
                subprocess.run([str(pg_ctl), '-D', str(cluster), '-l', str(DATA / 'postgres.log'),
                                '-o', f'-h 127.0.0.1 -p {PORT}', '-w', 'start'],
                               check=True, creationflags=flags)
                pg_started = True
            else:
                result = subprocess.run([str(pg_ctl), '-D', str(cluster), 'status'],
                                        capture_output=True, creationflags=flags)
                if result.returncode:
                    raise RuntimeError(f'Порт {PORT} занят другим PostgreSQL.')
            connection_args = dict(host=url.host, port=url.port, user=url.username,
                                   password=url.password, connect_timeout=5)
            with psycopg.connect(dbname='postgres', autocommit=True, **connection_args) as conn:
                if not conn.execute("SELECT 1 FROM pg_database WHERE datname='medhub'").fetchone():
                    conn.execute('CREATE DATABASE medhub')
        env['DATABASE_URL'] = url.render_as_string(hide_password=False)
        with psycopg.connect(dbname=url.database, host=url.host, port=url.port or 5432,
                             user=url.username, password=url.password, connect_timeout=5) as conn:
            assert conn.execute('SELECT current_database()').fetchone()[0] == 'medhub'
        with (DATA / 'migration.log').open('a', encoding='utf-8') as log:
            subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                           cwd=ROOT / 'backend', env=env, stdout=log, stderr=log,
                           check=True, creationflags=flags)
        commands = [
            ('api', [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8010'], ROOT / 'backend'),
            ('worker', [sys.executable, '-m', 'app.worker'], ROOT / 'backend'),
            ('ui', [node, str(vite), '--host', '127.0.0.1', '--port', '5173', '--strictPort'], ROOT / 'frontend'),
        ]
        for name, command, cwd in commands:
            log = (DATA / f'{name}.log').open('a', encoding='utf-8')
            logs.append(log)
            processes.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log,
                                              stderr=log, creationflags=flags))
        wait_http('http://127.0.0.1:8010/api/health', processes)
        wait_http('http://localhost:5173/api/health', processes)
        print('MedHub: http://localhost:5173 ; остановка: Ctrl+C', flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(2)
        raise RuntimeError('Один из сервисов остановился; проверьте data/local.')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for log in logs:
            log.close()
        if pg_started:
            subprocess.run([str(pg_ctl), '-D', str(DATA / 'postgres'), '-m', 'fast', '-w', 'stop'],
                           creationflags=flags)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as error:
        # Исключения соединения могут содержать реквизиты: наружу только тип.
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        else:
            print(f'Запуск не выполнен ({type(error).__name__}); проверьте data/local и .env.', file=sys.stderr)
        sys.exit(1)
