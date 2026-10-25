#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-kit :: chunk.py
遍历 corpus/<machine>/ 下配置的文本日志，构建 index/chunks.jsonl。
分块规则移植自 D:\\11\\Tools\\logs-corpus\\build.ps1（2026-10-18 验证过的策略）：
- 代码围栏外的 Markdown 标题切段，段内按空行聚合到约 aggregate_chars 字
- 超长段落按 window_chars 窗口、overlap_chars 重叠切分
- 正文 < min_chars 或纯分隔线的块丢弃
- exclude_names 中的规则文件（AGENTS.md/RULES.md）不分块
- extensions 支持 Markdown、纯文本、CSV 与终端日志
- 跨机器按文件内容 sha256 去重（同一文件在多台机器只保留一份，machines 记录来源）
"""
import datetime
import hashlib
import json
import os
import re
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(KIT, 'corpus')
INDEX = os.path.join(KIT, 'index')

CFG = json.load(open(os.path.join(KIT, 'config', 'kit.json'), encoding='utf-8'))
EXCLUDE = set(CFG.get('exclude_names', []))
CH = CFG.get('chunk', {})
AGG = CH.get('aggregate_chars', 700)
WINDOW = CH.get('window_chars', 1200)
OVERLAP = CH.get('overlap_chars', 120)
MIN_CHARS = CH.get('min_chars', 20)
EXTS = tuple(CH.get('extensions', ['.md']))

DATE_PREFIX_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})-(.+)$', re.IGNORECASE)
DATE_SEARCH_RE = re.compile(r'(20\d{2})[-_]?(\d{2})[-_]?(\d{2})')
SEP_RE = re.compile(r'^[\s\-=_*#>]+$')


def read_text(path):
    """Read common Windows text encodings without letting one bad byte abort ingest."""
    with open(path, 'rb') as handle:
        data = handle.read()
    for encoding in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


def file_meta(path):
    """Return (date, topic) from file name, falling back to mtime for undated logs."""
    filename = os.path.basename(path)
    stem = os.path.splitext(filename)[0]
    match = DATE_PREFIX_RE.match(stem)
    if match:
        return match.group(1), match.group(2)
    match = DATE_SEARCH_RE.search(stem)
    if match:
        try:
            value = datetime.date(*(int(part) for part in match.groups()))
            return value.isoformat(), stem
        except ValueError:
            pass
    try:
        value = datetime.date.fromtimestamp(os.path.getmtime(path))
        return value.isoformat(), stem
    except (OSError, OverflowError, ValueError):
        return None, stem


def split_blocks(text):
    """按代码围栏外的标题切段。返回 [(标题路径list, 段落文本)]，保持顺序。"""
    out, buf, cur_path, in_code = [], [], [], False
    for line in text.splitlines():
        if line.lstrip().startswith('```'):
            in_code = not in_code
            buf.append(line)
            continue
        if not in_code:
            m = re.match(r'^(#{1,6})\s+(.*)$', line)
            if m:
                if buf:
                    out.append((list(cur_path), '\n'.join(buf)))
                    buf = []
                level = len(m.group(1))
                cur_path = cur_path[:level - 1] + [m.group(2).strip()]
                continue
        buf.append(line)
    if buf:
        out.append((list(cur_path), '\n'.join(buf)))
    return out


def window_cut(text):
    """超长段落滑窗切分。"""
    if len(text) <= WINDOW:
        return [text]
    pieces, start = [], 0
    while start < len(text):
        pieces.append(text[start:start + WINDOW])
        if start + WINDOW >= len(text):
            break
        start += WINDOW - OVERLAP
    return pieces


def chunk_file(path):
    """返回该文件的块列表 [(headings, text)]。"""
    try:
        text = read_text(path)
    except OSError:
        return []
    blocks = split_blocks(text)
    chunks, agg, agg_path = [], [], None
    for path_list, para in blocks:
        if not para.strip():
            continue
        for piece in window_cut(para):
            t = piece.strip()
            if len(t) < MIN_CHARS or SEP_RE.match(t):
                continue
            if agg and sum(len(x) for x in agg) + len(t) > AGG:
                chunks.append((agg_path or [], '\n\n'.join(agg)))
                agg, agg_path = [], None
            if agg_path is None:
                agg_path = path_list
            agg.append(t)
    if agg:
        chunks.append((agg_path or [], '\n\n'.join(agg)))
    return chunks


def main():
    machines_dir = CORPUS
    if not os.path.isdir(machines_dir):
        sys.exit('corpus/ 不存在，先运行 collect.ps1')
    os.makedirs(INDEX, exist_ok=True)
    seen_sha = {}          # content sha -> chunk record（跨机去重）
    records = []
    n_files = 0
    for machine in sorted(os.listdir(machines_dir)):
        mdir = os.path.join(machines_dir, machine)
        if not os.path.isdir(mdir):
            continue
        for tag in sorted(os.listdir(mdir)):
            tdir = os.path.join(mdir, tag)
            if not os.path.isdir(tdir):
                continue
            for base, _dirs, files in os.walk(tdir):
                for fn in sorted(files):
                    if not fn.lower().endswith(EXTS) or fn in EXCLUDE:
                        continue
                    fp = os.path.join(base, fn)
                    rel = os.path.relpath(fp, tdir)
                    data = open(fp, 'rb').read()
                    sha = hashlib.sha256(data).hexdigest()
                    date, topic = file_meta(fp)
                    first = sha not in seen_sha
                    if first:
                        seen_sha[sha] = True
                    n_files += 1
                    src_key = machine + '/' + tag + '/' + rel.replace('\\', '/')
                    if not first:
                        # 同内容已入块：只给已有记录追加 machine 来源
                        for r in records:
                            if r['content_sha'] == sha and machine not in r['machines']:
                                r['machines'].append(machine)
                        continue
                    prefix = hashlib.sha1(src_key.encode('utf-8')).hexdigest()[:10]
                    for i, (headings, text) in enumerate(chunk_file(fp)):
                        embed_text = '[%s · %s] %s\n%s' % (
                            date or 'undated', topic, ' > '.join(headings), text)
                        records.append({
                            'id': '%s-%04d' % (prefix, i),
                            'content_sha': sha,
                            'machines': [machine],
                            'source': src_key,
                            'topic': topic,
                            'date': date,
                            'headings': headings,
                            'chars': len(text),
                            'text': text,
                            'embed_text': embed_text,
                        })
    records.sort(key=lambda r: (r['date'] or '', r['source'], r['id']))
    out = os.path.join(INDEX, 'chunks.jsonl')
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    total_chars = sum(r['chars'] for r in records)
    print('files=%d unique_files=%d chunks=%d chars=%d' % (
        n_files, len(seen_sha), len(records), total_chars))
    print('-> %s' % out)


if __name__ == '__main__':
    main()
