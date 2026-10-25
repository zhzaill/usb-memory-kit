#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Human-readable access to the raw log archive under corpus/."""
import io
import json
import os
import zipfile

from chunk import file_meta, read_text


class LogArchive:
    def __init__(self, root, extensions):
        self.root = os.path.realpath(root)
        self.extensions = tuple(x.lower() for x in extensions)

    def _safe_path(self, log_id):
        value = str(log_id or '').replace('\\', '/').strip()
        if not value or '\x00' in value:
            raise ValueError('invalid log id')
        path = os.path.realpath(os.path.join(self.root, value))
        if os.path.commonpath([self.root, path]) != self.root:
            raise ValueError('log path escapes archive')
        if not os.path.isfile(path):
            raise FileNotFoundError('log not found')
        if not path.lower().endswith(self.extensions):
            raise ValueError('unsupported log type')
        return path

    def _manifest_meta(self):
        result = {}
        if not os.path.isdir(self.root):
            return result
        for machine in os.listdir(self.root):
            manifest = os.path.join(self.root, machine, 'manifest.json')
            if not os.path.isfile(manifest):
                continue
            try:
                with open(manifest, encoding='utf-8') as handle:
                    items = json.load(handle)
            except (OSError, ValueError):
                continue
            for item in items:
                rel = str(item.get('relpath') or '').replace('\\', '/')
                tag = str(item.get('tag') or '')
                result[(machine, tag, rel)] = item
        return result

    def list(self, query='', extension='', limit=500):
        query = str(query or '').strip().lower()
        extension = str(extension or '').strip().lower()
        if extension and not extension.startswith('.'):
            extension = '.' + extension
        limit = min(max(int(limit), 1), 5000)
        manifests = self._manifest_meta()
        rows = []
        if not os.path.isdir(self.root):
            return {'files': [], 'stats': {'files': 0, 'bytes': 0, 'machines': []}}

        for base, dirs, files in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if d != '__pycache__')
            for filename in sorted(files):
                if filename == 'manifest.json' or not filename.lower().endswith(self.extensions):
                    continue
                path = os.path.join(base, filename)
                rel = os.path.relpath(path, self.root).replace('\\', '/')
                parts = rel.split('/')
                machine = parts[0] if parts else ''
                tag = parts[1] if len(parts) > 1 else ''
                archive_rel = '/'.join(parts[2:]) if len(parts) > 2 else filename
                ext = os.path.splitext(filename)[1].lower()
                if extension and ext != extension:
                    continue
                date, topic = file_meta(path)
                meta = manifests.get((machine, tag, archive_rel), {})
                try:
                    text = read_text(path)
                except OSError:
                    text = ''
                haystack = ' '.join([
                    filename, rel, topic, date or '', str(meta.get('root') or '')
                ]).lower()
                matched = not query or query in haystack or query in text.lower()
                if not matched:
                    continue
                excerpt = text.strip().replace('\r', '').replace('\n', ' ')[:220]
                if text:
                    folded = text.lower()
                    pos = folded.find(query) if query else -1
                    if pos >= 0:
                        start = max(0, pos - 80)
                        excerpt = text[start:start + 220].replace('\n', ' ').strip()
                stat = os.stat(path)
                row = {
                    'id': rel,
                    'machine': machine,
                    'tag': tag,
                    'name': filename,
                    'topic': topic,
                    'date': date,
                    'ext': ext,
                    'bytes': stat.st_size,
                    'modified_at': stat.st_mtime,
                    'source_root': meta.get('root') or '',
                    'excerpt': excerpt,
                }
                rows.append(row)

        rows.sort(key=lambda x: (x['date'] or '', x['modified_at'], x['id']), reverse=True)
        files_out = rows[:limit]
        return {
            'files': files_out,
            'stats': {
                'files': len(rows),
                'bytes': sum(x['bytes'] for x in rows),
                'machines': sorted({x['machine'] for x in rows if x['machine']}),
                'shown': len(files_out),
                'archive_root': self.root,
            },
        }

    def get(self, log_id):
        path = self._safe_path(log_id)
        date, topic = file_meta(path)
        text = read_text(path)
        stat = os.stat(path)
        return {
            'id': os.path.relpath(path, self.root).replace('\\', '/'),
            'name': os.path.basename(path),
            'topic': topic,
            'date': date,
            'ext': os.path.splitext(path)[1].lower(),
            'bytes': stat.st_size,
            'modified_at': stat.st_mtime,
            'text': text,
        }

    def path_for(self, log_id):
        return self._safe_path(log_id)

    def zip_bytes(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            if os.path.isdir(self.root):
                for base, dirs, files in os.walk(self.root):
                    dirs[:] = sorted(d for d in dirs if d != '__pycache__')
                    for filename in sorted(files):
                        if filename == 'manifest.json' or not filename.lower().endswith(self.extensions):
                            continue
                        path = os.path.join(base, filename)
                        arcname = os.path.relpath(path, self.root).replace('\\', '/')
                        bundle.write(path, arcname)
        return buffer.getvalue()
