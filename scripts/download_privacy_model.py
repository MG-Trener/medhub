"""Скачать только веса приватного NER; фиксировать revision и контрольные суммы."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    from huggingface_hub import HfApi, snapshot_download
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--revision', help='Exact upstream commit; omit to resolve once and record')
    args = parser.parse_args()
    model = 'urchade/gliner_multi-v2.1'
    revision = HfApi().model_info(model, revision=args.revision).sha
    snapshot_download(model, revision=revision, local_dir=str(args.directory),
        allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model'])
    manifest = {'repo': model, 'revision': revision, 'sha256': {}}
    for path in sorted(args.directory.rglob('*')):
        if path.is_file() and '.cache' not in path.parts and path.name != 'medhub-model-manifest.json':
            with path.open('rb') as file:
                manifest['sha256'][path.relative_to(args.directory).as_posix()] = hashlib.file_digest(file, 'sha256').hexdigest()
    (args.directory / 'medhub-model-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Local model downloaded; pinned revision:', revision)


if __name__ == '__main__':
    main()
