import os
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin')
sys.path.insert(0, BIN)

from chunk import anchor_id, file_meta, read_text  # noqa: E402


class ChunkMetadataTests(unittest.TestCase):
    def test_prefix_date_is_normalized(self):
        date, topic = file_meta(r'C:\logs\2026-10-24-memory-review.md')
        self.assertEqual(date, '2026-10-24')
        self.assertEqual(topic, 'memory-review')

    def test_compact_date_inside_terminal_log_name(self):
        date, topic = file_meta(r'C:\logs\router-uart-boot-20261015-221500.log')
        self.assertEqual(date, '2026-10-15')
        self.assertEqual(topic, 'router-uart-boot-20261015-221500')

    def test_gb18030_text_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'legacy.log')
            with open(path, 'wb') as handle:
                handle.write('中文日志'.encode('gb18030'))
            self.assertEqual(read_text(path), '中文日志')

    def test_named_anchor_is_not_a_dated_log(self):
        self.assertEqual(anchor_id('LAPTOP/anchor-ai-workspace-rules/docs/quickstart.md'), 'ai-workspace-rules')
        self.assertIsNone(anchor_id('LAPTOP/r0/2026-10-26-note.md'))


if __name__ == '__main__':
    unittest.main()
