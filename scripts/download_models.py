"""Скачать модели на GPU-ПК. HF_TOKEN считывается из окружения, не выводится."""
import argparse
import os
from pathlib import Path
from huggingface_hub import snapshot_download

parser = argparse.ArgumentParser()
parser.add_argument('--directory', required=True)
args = parser.parse_args()
root = Path(args.directory)
root.mkdir(parents=True, exist_ok=True)
snapshot_download('Systran/faster-whisper-large-v3', local_dir=root / 'faster-whisper-large-v3')
snapshot_download('pyannote/speaker-diarization-community-1', token=os.environ.get('HF_TOKEN'), local_dir=root / 'pyannote-speaker-diarization-community-1')
print('Модели сохранены. Проверьте offline-загрузку из каталога на GPU-ПК.')
