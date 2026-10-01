"""Изолированный self-hosted ASR для ПК с GPU; API защищён Bearer-токеном."""
import os
import secrets
import tempfile
import threading
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from .providers import transcribe
from .config import settings

app = FastAPI(title='medhub private ASR', docs_url=None, redoc_url=None)
slot = threading.BoundedSemaphore(1)


@app.get('/health')
def health():
    return {'status': 'ok', 'models': 'loaded on first transcription'}


@app.post('/transcribe')
def speech(file: UploadFile = File(...), authorization: str = Header('')):
    key = os.environ.get('ASR_SERVICE_TOKEN', '')
    if len(key) < 32 or not secrets.compare_digest(authorization, 'Bearer ' + key):
        raise HTTPException(401, 'Invalid ASR credential')
    if not slot.acquire(blocking=False):
        raise HTTPException(429, 'GPU is busy; retry later')
    try:
        with tempfile.TemporaryDirectory(prefix='medhub-asr-') as tmp:
            path = Path(tmp) / 'recording.audio'
            size = 0
            with path.open('wb') as target:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings().max_audio_mb * 1024 * 1024:
                        raise HTTPException(413, 'Audio too large')
                    target.write(chunk)
            if size < 32:
                raise HTTPException(422, 'Empty audio')
            return {'segments': transcribe(path)}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'ASR failed. Check model paths and GPU runtime.')
    finally:
        slot.release()


from pydantic import BaseModel, Field
from .privacy_gate import local_private_text, ner


class PrivateTexts(BaseModel):
    texts: list[str] = Field(max_length=2200)


@app.post('/redact')
def redact_private(body: PrivateTexts, authorization: str = Header('')):
    key = os.environ.get('ASR_SERVICE_TOKEN', '')
    if len(key) < 32 or not secrets.compare_digest(authorization, 'Bearer ' + key):
        raise HTTPException(401, 'Invalid privacy credential')
    if sum(len(t) for t in body.texts) > 400000:
        raise HTTPException(413, 'Context too large')
    if not slot.acquire(blocking=False):
        raise HTTPException(429, 'Privacy service is busy')
    try:
        return {'texts': [local_private_text(text) for text in body.texts]}
    except Exception:
        raise HTTPException(503, 'Local privacy model unavailable; external processing blocked.') from None
    finally:
        slot.release()


@app.get('/ready')
def ready(authorization: str = Header('')):
    key = os.environ.get('ASR_SERVICE_TOKEN', '')
    if len(key) < 32 or not secrets.compare_digest(authorization, 'Bearer ' + key):
        raise HTTPException(401, 'Invalid ASR credential')
    from .providers import whisper, diarizer
    try:
        whisper(); diarizer(); ner()
        return {'status': 'ready', 'asr': True, 'privacy': True}
    except Exception:
        raise HTTPException(503, 'Models unavailable') from None
