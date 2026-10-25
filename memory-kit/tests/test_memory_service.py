import os
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin')
sys.path.insert(0, BIN)

from memory_service import (  # noqa: E402
    MemoryNotFound,
    MemoryProtocolError,
    MemoryQuery,
    MemoryService,
)


class FakeIndex:
    def __init__(self):
        self.cfg = {
            'memory': {
                'state_dir': 'state',
                'sessions': {'max_turns': 2, 'ttl_days': 30},
                'context': {
                    'ttl_seconds': 900,
                    'max_items': 10,
                    'max_chars': 1200,
                    'hard_max_chars': 3000,
                },
            },
        }
        self.by_id = {
            'hit-1': {
                'id': 'hit-1',
                'topic': 'Memory architecture',
                'date': '2026-10-24',
                'source': 'LAPTOP/Logs/2026-10-24-memory.md',
                'machines': ['LAPTOP'],
                'text': 'The shared core normalizes memory requests before retrieval.',
            },
        }

    def search(self, **_kwargs):
        return {
            'query': 'memory',
            'mode': 'hybrid',
            'degraded': False,
            'k': 8,
            'results': [{
                'id': 'hit-1',
                'topic': 'Memory architecture',
                'date': '2026-10-24',
                'source': 'LAPTOP/Logs/2026-10-24-memory.md',
                'machines': ['LAPTOP'],
                'preview': 'The shared core normalizes memory requests before retrieval.',
            }],
        }


class MemoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.index = FakeIndex()
        self.service = MemoryService(self.index, self.tmp.name, self.index.cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_protocol_adapters_normalize_to_same_query(self):
        http = MemoryQuery.from_payload({
            'q': 'memory',
            'k': 8,
            'mode': 'hybrid',
            'from': '2026-10-01',
            'to': '2026-10-31',
            'machine': 'LAPTOP',
        }, protocol='http')
        mcp = MemoryQuery.from_payload({
            'query': 'memory',
            'k': 8,
            'mode': 'hybrid',
            'date_from': '2026-10-01',
            'date_to': '2026-10-31',
            'machine': 'LAPTOP',
        }, protocol='mcp')
        self.assertEqual(http, mcp)
        self.assertEqual(http.core_args()['date_from'], '2026-10-01')

    def test_query_validation_is_shared(self):
        with self.assertRaises(MemoryProtocolError):
            MemoryQuery.from_payload({'q': ''}, protocol='http')
        with self.assertRaises(MemoryProtocolError):
            MemoryQuery.from_payload({'query': 'x', 'mode': 'other'}, protocol='mcp')

    def test_sessions_are_bounded_persistent_and_owner_scoped(self):
        session = self.service.create_session({'owner': 'alice', 'title': 'Work'})
        sid = session['id']
        for role, content in [
            ('user', 'one'),
            ('assistant', 'two'),
            ('user', 'three'),
        ]:
            self.service.append_turn('alice', sid, {'role': role, 'content': content})

        loaded = self.service.get_session('alice', sid)
        self.assertEqual([turn['content'] for turn in loaded['turns']], ['two', 'three'])
        self.assertEqual(loaded['revision'], 4)
        with self.assertRaises(MemoryNotFound):
            self.service.get_session('bob', sid)

    def test_context_combines_working_and_long_term_memory(self):
        session = self.service.create_session({'owner': 'alice', 'title': 'Memory'})
        sid = session['id']
        self.service.append_turn('alice', sid, {
            'role': 'user',
            'content': 'We chose a protocol-neutral memory core.',
        })
        context = self.service.build_context({
            'owner': 'alice',
            'session_id': sid,
            'query': 'memory architecture',
            'max_chars': 1200,
        })

        self.assertIn('Owner: alice', context['text'])
        self.assertIn('We chose a protocol-neutral memory core.', context['text'])
        self.assertIn('## Long-term Memory', context['text'])
        self.assertEqual(context['citations'][0]['id'], 'hit-1')
        self.assertEqual(context['turns_included'], 1)
        self.assertGreater(context['chars'], 100)

        fetched = self.service.get_context('alice', context['id'])
        self.assertEqual(fetched['text'], context['text'])
        with self.assertRaises(MemoryNotFound):
            self.service.get_context('bob', context['id'])

    def test_context_without_session_keeps_requested_owner(self):
        context = self.service.build_context({
            'owner': 'carol',
            'query': 'memory architecture',
            'max_chars': 1200,
        })
        self.assertIn('Owner: carol', context['text'])
        self.assertIsNone(context['session_id'])


if __name__ == '__main__':
    unittest.main()
