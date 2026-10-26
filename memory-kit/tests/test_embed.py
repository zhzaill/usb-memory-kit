import os
import sys
import unittest
from unittest.mock import Mock, patch

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin')
sys.path.insert(0, BIN)

from embed import embed_texts  # noqa: E402


class EmbeddingResponseTests(unittest.TestCase):
    def test_rejects_incomplete_batch(self):
        response = Mock()
        response.json.return_value = {'data': [{'index': 0, 'embedding': [0.1] * 1024}]}
        response.raise_for_status.return_value = None
        with patch('embed.requests.post', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'count mismatch'):
                embed_texts({'url': 'http://unused'}, ['a', 'b'])

    def test_rejects_wrong_vector_dimension(self):
        response = Mock()
        response.json.return_value = {'data': [{'index': 0, 'embedding': [0.1]}]}
        response.raise_for_status.return_value = None
        with patch('embed.requests.post', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'dimension mismatch'):
                embed_texts({'url': 'http://unused'}, ['a'])


if __name__ == '__main__':
    unittest.main()
