#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-kit :: memory_service.py

Protocol-neutral memory gateway inspired by ds2api's adapter boundary:
payload -> normalized MemoryQuery/MemoryTurn -> shared memory core -> renderer.

Long-term memory remains the immutable log corpus indexed by kitcore.
Short-term working memory is stored as bounded, owner-scoped sessions.
Context packs are cached in memory with a TTL and owner isolation.
"""
import datetime as _dt
import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field


SESSION_ID_RE = re.compile(r'^mem_[0-9a-f]{32}$')
ROLES = {'system', 'user', 'assistant', 'tool'}
DEFAULT_OWNER = 'default'


class MemoryProtocolError(ValueError):
    pass


class MemoryNotFound(LookupError):
    pass


def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _future_iso(days):
    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=days)).replace(
        microsecond=0).isoformat()


def _as_text(value, name, required=False, max_len=200000):
    text = '' if value is None else str(value).strip()
    if required and not text:
        raise MemoryProtocolError('%s is required' % name)
    if len(text) > max_len:
        raise MemoryProtocolError('%s exceeds %d characters' % (name, max_len))
    return text


def _owner(value):
    owner = _as_text(value, 'owner', max_len=128) or DEFAULT_OWNER
    if '\x00' in owner:
        raise MemoryProtocolError('owner contains an invalid character')
    return owner


def _session_id(value):
    sid = _as_text(value, 'session_id', required=True, max_len=64)
    if not SESSION_ID_RE.match(sid):
        raise MemoryProtocolError('invalid session_id')
    return sid


def _context_id(value):
    cid = _as_text(value, 'context_id', required=True, max_len=64)
    if not cid.startswith('ctx_') or len(cid) != 36:
        raise MemoryProtocolError('invalid context_id')
    return cid


def _int_range(value, name, default, low, high):
    if value in (None, ''):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise MemoryProtocolError('%s must be an integer' % name)
    if number < low or number > high:
        raise MemoryProtocolError('%s must be between %d and %d' % (name, low, high))
    return number


def _date(value, name):
    text = _as_text(value, name, max_len=10)
    if not text:
        return None
    try:
        return _dt.date.fromisoformat(text).isoformat()
    except ValueError:
        raise MemoryProtocolError('%s must use YYYY-MM-DD' % name)


def _atomic_write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


@dataclass(frozen=True)
class MemoryQuery:
    query: str
    k: int = 10
    mode: str = 'hybrid'
    machine: str = ''
    date_from: str = ''
    date_to: str = ''
    topic: str = ''

    @classmethod
    def from_payload(cls, payload, protocol='http'):
        payload = payload or {}
        if protocol == 'mcp':
            return cls(
                query=_as_text(payload.get('query'), 'query', required=True, max_len=4000),
                k=_int_range(payload.get('k'), 'k', 8, 1, 50),
                mode=_normalize_mode(payload.get('mode')),
                machine=_as_text(payload.get('machine'), 'machine', max_len=128),
                date_from=_date(payload.get('date_from'), 'date_from') or '',
                date_to=_date(payload.get('date_to'), 'date_to') or '',
                topic=_as_text(payload.get('topic'), 'topic', max_len=200),
            )
        if protocol in ('http', 'generic'):
            raw_query = payload.get('q')
            if raw_query is None:
                raw_query = payload.get('query')
            return cls(
                query=_as_text(raw_query, 'query', required=True, max_len=4000),
                k=_int_range(payload.get('k'), 'k', 10, 1, 50),
                mode=_normalize_mode(payload.get('mode')),
                machine=_as_text(payload.get('machine'), 'machine', max_len=128),
                date_from=_date(payload.get('from') or payload.get('date_from'), 'date_from') or '',
                date_to=_date(payload.get('to') or payload.get('date_to'), 'date_to') or '',
                topic=_as_text(payload.get('topic'), 'topic', max_len=200),
            )
        raise MemoryProtocolError('unsupported protocol: %s' % protocol)

    def core_args(self):
        return {
            'q': self.query,
            'k': self.k,
            'mode': self.mode,
            'machine': self.machine or None,
            'date_from': self.date_from or None,
            'date_to': self.date_to or None,
            'topic': self.topic or None,
        }


@dataclass(frozen=True)
class MemoryTurn:
    role: str
    content: str
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload):
        payload = payload or {}
        role = _as_text(payload.get('role'), 'role', required=True, max_len=32).lower()
        if role == 'developer':
            role = 'system'
        if role not in ROLES:
            raise MemoryProtocolError('role must be one of: %s' % ', '.join(sorted(ROLES)))
        content = _as_text(payload.get('content'), 'content', required=True)
        metadata = payload.get('metadata') or {}
        if not isinstance(metadata, dict):
            raise MemoryProtocolError('metadata must be an object')
        if len(json.dumps(metadata, ensure_ascii=False)) > 20000:
            raise MemoryProtocolError('metadata is too large')
        return cls(role=role, content=content, metadata=metadata)


def _normalize_mode(value):
    mode = _as_text(value, 'mode', max_len=16).lower() or 'hybrid'
    if mode not in ('hybrid', 'dense', 'sparse'):
        raise MemoryProtocolError('mode must be hybrid, dense or sparse')
    return mode


class SessionStore:
    """Bounded owner-scoped working memory with atomic JSON persistence."""

    def __init__(self, root, max_turns=40, ttl_days=30):
        self.root = root
        self.max_turns = int(max_turns)
        self.ttl_days = max(1, int(ttl_days))
        self._lock = threading.RLock()

    def _owner_dir(self, owner):
        digest = hashlib.sha256(owner.encode('utf-8')).hexdigest()[:20]
        return os.path.join(self.root, digest)

    def _path(self, owner, session_id):
        return os.path.join(self._owner_dir(owner), session_id + '.json')

    def _read(self, owner, session_id):
        path = self._path(owner, session_id)
        if not os.path.exists(path):
            raise MemoryNotFound('session not found')
        try:
            with open(path, encoding='utf-8') as handle:
                item = json.load(handle)
        except (OSError, ValueError) as exc:
            raise MemoryProtocolError('cannot read session: %s' % exc)
        if item.get('owner') != owner:
            raise MemoryNotFound('session not found')
        return item

    def _write(self, item):
        path = self._path(item['owner'], item['id'])
        _atomic_write(path, json.dumps(item, ensure_ascii=False, indent=1) + '\n')

    def _expired(self, item):
        try:
            expires = _dt.datetime.fromisoformat(item['expires_at'])
        except (KeyError, TypeError, ValueError):
            return True
        return expires <= _dt.datetime.now(_dt.timezone.utc)

    def create(self, owner, title=''):
        owner = _owner(owner)
        title = _as_text(title, 'title', max_len=120) or 'Memory session'
        now = _now_iso()
        item = {
            'version': 1,
            'id': 'mem_' + uuid.uuid4().hex,
            'owner': owner,
            'title': title,
            'created_at': now,
            'updated_at': now,
            'expires_at': _future_iso(self.ttl_days),
            'revision': 1,
            'turns': [],
        }
        with self._lock:
            self._write(item)
        return item

    def get(self, owner, session_id, sweep=True):
        owner = _owner(owner)
        session_id = _session_id(session_id)
        with self._lock:
            item = self._read(owner, session_id)
            if sweep and self._expired(item):
                try:
                    os.remove(self._path(owner, session_id))
                except OSError:
                    pass
                raise MemoryNotFound('session expired')
            return item

    def append(self, owner, session_id, turn):
        owner = _owner(owner)
        session_id = _session_id(session_id)
        if not isinstance(turn, MemoryTurn):
            turn = MemoryTurn.from_payload(turn)
        with self._lock:
            item = self.get(owner, session_id)
            item['turns'].append({
                'role': turn.role,
                'content': turn.content,
                'metadata': turn.metadata,
                'at': _now_iso(),
            })
            if len(item['turns']) > self.max_turns:
                item['turns'] = item['turns'][-self.max_turns:]
            item['revision'] = int(item.get('revision', 0)) + 1
            item['updated_at'] = _now_iso()
            item['expires_at'] = _future_iso(self.ttl_days)
            self._write(item)
            return item

    def delete(self, owner, session_id):
        owner = _owner(owner)
        session_id = _session_id(session_id)
        with self._lock:
            self.get(owner, session_id)
            os.remove(self._path(owner, session_id))

    def list(self, owner, limit=50):
        owner = _owner(owner)
        limit = _int_range(limit, 'limit', 50, 1, 200)
        folder = self._owner_dir(owner)
        items = []
        with self._lock:
            if not os.path.isdir(folder):
                return []
            for name in os.listdir(folder):
                if not name.endswith('.json'):
                    continue
                sid = name[:-5]
                if not SESSION_ID_RE.match(sid):
                    continue
                try:
                    item = self._read(owner, sid)
                except (MemoryNotFound, MemoryProtocolError):
                    continue
                if self._expired(item):
                    try:
                        os.remove(self._path(owner, sid))
                    except OSError:
                        pass
                    continue
                items.append({
                    'id': item['id'],
                    'owner': item['owner'],
                    'title': item.get('title', ''),
                    'created_at': item.get('created_at'),
                    'updated_at': item.get('updated_at'),
                    'expires_at': item.get('expires_at'),
                    'revision': item.get('revision', 0),
                    'turn_count': len(item.get('turns', [])),
                })
        items.sort(key=lambda x: (x.get('updated_at') or '', x['id']), reverse=True)
        return items[:limit]


class ContextCache:
    """In-memory owner-scoped TTL store, mirroring ds2api's response store."""

    def __init__(self, ttl_seconds=900, max_items=256):
        self.ttl_seconds = max(30, int(ttl_seconds))
        self.max_items = max(1, int(max_items))
        self._lock = threading.Lock()
        self._items = {}

    def _sweep_locked(self, now):
        expired = [key for key, item in self._items.items() if item['expires_at'] <= now]
        for key in expired:
            del self._items[key]
        while len(self._items) > self.max_items:
            oldest = min(self._items, key=lambda key: self._items[key]['created_at'])
            del self._items[oldest]

    def put(self, owner, value):
        now = time.time()
        item = {
            'id': 'ctx_' + uuid.uuid4().hex,
            'owner': owner,
            'value': value,
            'created_at': now,
            'expires_at': now + self.ttl_seconds,
        }
        with self._lock:
            self._sweep_locked(now)
            self._items[(owner, item['id'])] = item
        return item

    def get(self, owner, context_id):
        now = time.time()
        with self._lock:
            self._sweep_locked(now)
            item = self._items.get((owner, context_id))
            if item is None:
                return None
            return item

    def stats(self):
        now = time.time()
        with self._lock:
            self._sweep_locked(now)
            return {'items': len(self._items), 'ttl_seconds': self.ttl_seconds}


class MemoryService:
    def __init__(self, index, kit_root, config=None):
        self.index = index
        self.kit_root = kit_root
        cfg = (config or {}).get('memory', {})
        session_cfg = cfg.get('sessions', {})
        context_cfg = cfg.get('context', {})
        state_dir = cfg.get('state_dir', 'state')
        if not os.path.isabs(state_dir):
            state_dir = os.path.join(kit_root, state_dir)
        self.sessions = SessionStore(
            os.path.join(state_dir, 'sessions'),
            max_turns=session_cfg.get('max_turns', 40),
            ttl_days=session_cfg.get('ttl_days', 30),
        )
        self.contexts = ContextCache(
            ttl_seconds=context_cfg.get('ttl_seconds', 900),
            max_items=context_cfg.get('max_items', 256),
        )
        self.default_context_chars = int(context_cfg.get('max_chars', 6000))
        self.max_context_chars = int(context_cfg.get('hard_max_chars', 30000))

    def search(self, payload, protocol='http'):
        request = MemoryQuery.from_payload(payload, protocol=protocol)
        result = self.index.search(**request.core_args())
        result = dict(result)
        result['object'] = 'memory.search'
        result['query'] = request.query
        result['protocol'] = protocol
        return result

    def create_session(self, payload):
        payload = payload or {}
        return self.sessions.create(payload.get('owner'), payload.get('title'))

    def get_session(self, owner, session_id):
        return self.sessions.get(owner, session_id)

    def list_sessions(self, owner, limit=50):
        return self.sessions.list(owner, limit=limit)

    def append_turn(self, owner, session_id, payload):
        turn = MemoryTurn.from_payload(payload)
        return self.sessions.append(owner, session_id, turn)

    def delete_session(self, owner, session_id):
        self.sessions.delete(owner, session_id)

    def build_context(self, payload):
        payload = payload or {}
        owner = _owner(payload.get('owner'))
        session_id = _as_text(payload.get('session_id'), 'session_id', max_len=64)
        if session_id:
            session_id = _session_id(session_id)
        query_payload = {
            'q': payload.get('query') or payload.get('q'),
            'k': payload.get('k', 8),
            'mode': payload.get('mode', 'hybrid'),
            'machine': payload.get('machine'),
            'from': payload.get('from') or payload.get('date_from'),
            'to': payload.get('to') or payload.get('date_to'),
            'topic': payload.get('topic'),
        }
        query = MemoryQuery.from_payload(query_payload, protocol='http')
        max_chars = _int_range(
            payload.get('max_chars'), 'max_chars', self.default_context_chars, 500,
            self.max_context_chars)

        result = self.index.search(**query.core_args())
        session = self.sessions.get(owner, session_id) if session_id else None
        text, citations, included_turns = self._pack_context(
            owner, query, result, session, max_chars)
        value = {
            'object': 'memory.context',
            'owner': owner,
            'query': query.query,
            'session_id': session_id or None,
            'text': text,
            'citations': citations,
            'turns_included': included_turns,
            'chars': len(text),
            'degraded': bool(result.get('degraded')),
        }
        cached = self.contexts.put(owner, value)
        out = dict(value)
        out['id'] = cached['id']
        out['expires_at'] = _dt.datetime.fromtimestamp(
            cached['expires_at'], _dt.timezone.utc).replace(microsecond=0).isoformat()
        return out

    def get_context(self, owner, context_id):
        owner = _owner(owner)
        context_id = _context_id(context_id)
        item = self.contexts.get(owner, context_id)
        if item is None:
            raise MemoryNotFound('context not found or expired')
        out = dict(item['value'])
        out['id'] = context_id
        out['expires_at'] = _dt.datetime.fromtimestamp(
            item['expires_at'], _dt.timezone.utc).replace(microsecond=0).isoformat()
        return out

    def stats(self):
        return {
            'sessions': 'persistent-owner-scoped',
            'contexts': self.contexts.stats(),
            'default_context_chars': self.default_context_chars,
        }

    def _pack_context(self, owner, query, result, session, max_chars):
        citations = []
        lines = [
            '# MEMORY_CONTEXT.md',
            '',
            'Owner: %s' % owner,
            'Query: %s' % query.query,
            'Generated: %s' % _now_iso(),
            '',
            '## Working Memory',
        ]
        included_turns = 0
        if session and session.get('turns'):
            selected = []
            used = 0
            budget = max(400, int(max_chars * 0.4))
            for turn in reversed(session['turns']):
                block = '=== %s ===\n%s\n\n' % (turn['role'].upper(), turn['content'])
                if selected and used + len(block) > budget:
                    break
                selected.append(block)
                used += len(block)
            selected.reverse()
            included_turns = len(selected)
            if selected:
                lines.extend(''.join(selected).rstrip().splitlines())
            else:
                lines.append('(no turns fit)')
        else:
            lines.append('(none)')

        lines.extend(['', '## Long-term Memory'])
        for hit in result.get('results', []):
            record = self.index.by_id.get(hit.get('id'), {})
            body = record.get('text') or hit.get('preview') or ''
            block = (
                '### %s · %s\n'
                '- id: %s\n'
                '- source: %s\n'
                '- date: %s\n'
                '- machines: %s\n\n'
                '%s\n\n'
            ) % (
                hit.get('date') or 'undated',
                hit.get('topic') or '(untitled)',
                hit.get('id'),
                hit.get('source'),
                hit.get('date') or '',
                ','.join(hit.get('machines') or []),
                body,
            )
            if len('\n'.join(lines)) + len(block) > max_chars:
                break
            lines.extend(block.rstrip().splitlines())
            citations.append({
                'id': hit.get('id'),
                'topic': hit.get('topic'),
                'date': hit.get('date'),
                'source': hit.get('source'),
            })
        if not citations:
            lines.append('(no long-term memory hit)')
        text = '\n'.join(lines)
        if len(text) > max_chars:
            text = text[:max_chars - 3].rstrip() + '...'
        return text, citations, included_turns
