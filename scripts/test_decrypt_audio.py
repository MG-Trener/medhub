"""Проверки экспорта только на синтетических данных."""
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from decrypt_audio import export_archive, extension


class DecryptAudioTests(unittest.TestCase):
    def test_export_retry_corruption_and_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, target = root / 'encrypted', root / 'plain'
            source.mkdir()
            key = Fernet.generate_key()
            audio = b'RIFF\x00\x00\x00\x00WAVEsynthetic'
            encrypted = Fernet(key).encrypt(audio)
            (source / 'one.enc').write_bytes(encrypted)
            (source / 'broken.enc').write_bytes(b'not encrypted')
            results = export_archive(source, target, key)
            self.assertEqual([r['status'] for r in results], ['error', 'exported'])
            self.assertEqual((target / 'one.wav').read_bytes(), audio)
            self.assertEqual((source / 'one.enc').read_bytes(), encrypted)
            self.assertEqual(export_archive(source, target, key)[1]['status'], 'already_exported')
            (target / 'one.wav').write_bytes(b'keep me')
            self.assertEqual(export_archive(source, target, key)[1]['status'], 'error')
            self.assertEqual((target / 'one.wav').read_bytes(), b'keep me')
            self.assertTrue(all(r['status'] == 'error' for r in export_archive(source, root / 'wrong', Fernet.generate_key())))
            with self.assertRaises(ValueError):
                export_archive(source, source / 'nested', key)

    def test_formats(self):
        for data, expected in [(b'OggS', '.ogg'), (b'fLaC', '.flac'),
                               (b'ID3', '.mp3'), (b'\x1aE\xdf\xa3', '.webm'),
                               (b'1234ftyp', '.mp4'), (b'unknown', '.bin')]:
            self.assertEqual(extension(data), expected)


if __name__ == '__main__':
    unittest.main()
