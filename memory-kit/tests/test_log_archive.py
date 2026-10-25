import os
import sys
import tempfile
import unittest
import zipfile
import io

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin')
sys.path.insert(0, BIN)

from log_archive import LogArchive  # noqa: E402


class LogArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        folder = os.path.join(root, 'MACHINE', 'r0')
        os.makedirs(folder)
        with open(os.path.join(folder, '2026-10-25-example.md'), 'w', encoding='utf-8') as handle:
            handle.write('# Example\n\nSearchable text.\n')
        with open(os.path.join(root, 'MACHINE', 'manifest.json'), 'w', encoding='utf-8') as handle:
            handle.write('[]')
        self.archive = LogArchive(root, ['.md', '.log'])

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_and_reads_raw_log(self):
        result = self.archive.list()
        self.assertEqual(result['stats']['files'], 1)
        item = result['files'][0]
        self.assertEqual(item['date'], '2026-10-25')
        detail = self.archive.get(item['id'])
        self.assertIn('Searchable text.', detail['text'])

    def test_content_filter_and_zip(self):
        self.assertEqual(len(self.archive.list('searchable')['files']), 1)
        data = self.archive.zip_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            names = bundle.namelist()
        self.assertIn('MACHINE/r0/2026-10-25-example.md', names)

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            self.archive.get('../outside.md')


if __name__ == '__main__':
    unittest.main()
