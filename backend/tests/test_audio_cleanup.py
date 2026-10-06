import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import event

from app import audio_cleanup
from app.config import settings
from app.db import Job, SessionLocal, engine
from test_workflow import patient, encounter


def test_cleanup_preserves_archive_and_only_reads_payload(client, doctor, monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), 'audio_dir', str(tmp_path))
    e = encounter(client, patient(client))
    protected = []
    with SessionLocal() as db:
        for kind in ('transcribe', 'mute_audio', 'cloud_asr', 'live_chunk'):
            for state in ('queued', 'running', 'done', 'failed'):
                payload = {}
                for key in ('audio', 'masked_audio'):
                    path = tmp_path / f'{kind}-{state}-{key}.enc'
                    path.write_bytes(b'synthetic encrypted audio')
                    os.utime(path, (1, 1))
                    protected.append(path)
                    payload[key] = str(path)
                db.add(Job(encounter_id=e['id'], kind=kind, state=state, payload=payload))
        db.commit()
    orphan = tmp_path / 'orphan.enc'
    orphan.write_bytes(b'synthetic')
    os.utime(orphan, (1, 1))
    recent = tmp_path / 'recent.enc'
    recent.write_bytes(b'synthetic')
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        audio_cleanup.cleanup()
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert all(path.exists() for path in protected)
    assert recent.exists() and not orphan.exists()
    assert len(statements) == 1
    assert statements[0].split('FROM')[0].strip() == 'SELECT jobs.payload'


def test_cleanup_without_old_files_does_not_connect(monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), 'audio_dir', str(tmp_path))
    (tmp_path / 'recent.enc').write_bytes(b'synthetic')
    def forbidden():
        pytest.fail('Cleanup must not query the database without old files')
    monkeypatch.setattr(audio_cleanup, 'SessionLocal', forbidden)
    audio_cleanup.cleanup()


@pytest.mark.parametrize('fails', [False, True])
def test_cleanup_runs_at_most_hourly_even_after_failure(monkeypatch, fails):
    monkeypatch.setattr(audio_cleanup, '_next_cleanup', 0)
    clock = [100.0]
    calls = []
    monkeypatch.setattr(audio_cleanup.time, 'monotonic', lambda: clock[0])
    def clean():
        calls.append(clock[0])
        if fails:
            raise RuntimeError('Synthetic database outage')
    monkeypatch.setattr(audio_cleanup, 'cleanup', clean)
    for tick in (100, 102, 110, 3699, 3700):
        clock[0] = tick
        try:
            audio_cleanup.cleanup_if_due()
        except RuntimeError:
            assert fails
    assert calls == [100, 3700]


def test_database_failure_keeps_orphans(monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), 'audio_dir', str(tmp_path))
    path = tmp_path / 'old.enc'
    path.write_bytes(b'synthetic')
    os.utime(path, (1, 1))
    def unavailable():
        raise RuntimeError('Synthetic database outage')
    monkeypatch.setattr(audio_cleanup, 'SessionLocal', unavailable)
    with pytest.raises(RuntimeError):
        audio_cleanup.cleanup()
    assert path.exists()


def test_disabled_backup_exits_before_database_import():
    script = Path(__file__).resolve().parents[2] / 'deploy' / 'backup-database.py'
    result = subprocess.run([sys.executable, str(script)], env={
        **os.environ, 'MEDHUB_DATABASE_BACKUP_ENABLED': 'false',
        'DATABASE_URL': 'invalid://must-not-connect',
    }, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'Database backup skipped' in result.stdout
