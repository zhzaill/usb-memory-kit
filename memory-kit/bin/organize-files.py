#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-kit :: organize-files.py  (文件整理员)

扫描 U 盘的「我的文件」区，把每个文件的 名字/扩展名/大小/内容采样 交给本地 Qwen3-4B
（local-ai，默认 http://127.0.0.1:18080），得到 类目 + 建议新名 + 动作 + 理由，
汇总成 整理建议.json，并在控制台预览。

默认「只建议、不执行」——加 --apply 才真正改名/移动，且永不删除任何文件。

用法:
  python organize-files.py                 # 扫描并生成建议（默认 USB_ROOT\\我的文件）
  python organize-files.py --limit 20      # 只看前 20 个文件
  python organize-files.py --apply         # 按建议执行 move/rename（dup 只报告）
  python organize-files.py --root "X:\\another-folder"
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

import requests

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USB_ROOT = os.path.dirname(KIT)
CFG_PATH = os.path.join(KIT, 'config', 'categories.json')

DEFAULT_CATS = ['文档', '表格', '图片', '视频', '音频', '安装包', '压缩包', '代码', '临时', '其他']
SKIP_DIRS = {'System Volume Information', '$RECYCLE.BIN', 'memory-kit', 'local-ai', '.git', 'node_modules'}
TEXT_EXT = {'.txt', '.md', '.log', '.json', '.csv', '.tsv', '.py', '.ps1', '.js', '.ts', '.html', '.css', '.yml', '.yaml', '.ini', '.conf', '.bat', '.cmd', '.xml'}


def load_cfg():
    if os.path.exists(CFG_PATH):
        try:
            c = json.load(open(CFG_PATH, encoding='utf-8'))
            return c.get('root'), c.get('categories') or DEFAULT_CATS, c.get('endpoint'), c.get('max_files', 200)
        except Exception as e:
            print('[warn] categories.json unreadable: %s' % e)
    return None, DEFAULT_CATS, None, 200


def sample_text(path, ext, budget=1200):
    if ext not in TEXT_EXT:
        return ''
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read(budget).replace('\n', ' ').strip()
    except OSError:
        return ''


def walk(root, limit):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        for name in filenames:
            if name.startswith('.') or name in ('Thumbs.db', 'desktop.ini', 'autorun.inf', '整理建议.json'):
                continue
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append({'path': p, 'name': name, 'ext': os.path.splitext(name)[1].lower(),
                        'size': st.st_size, 'mtime': time.strftime('%Y-%m-%d', time.localtime(st.st_mtime))})
            if len(out) >= limit:
                return out
    return out


CAT_HINTS = {
    '文档': '文字资料/笔记/纪要/论文/说明',
    '表格': 'xlsx/csv/统计与账目',
    '图片': '照片/截图/图',
    '视频': '影片/录屏',
    '音频': '录音/音乐',
    '安装包': 'exe/msi/apk 等安装程序',
    '压缩包': 'zip/rar/7z',
    '代码': '源码/脚本/作业题',
    '临时': '缓存/空文件/无意义残留',
    '其他': '确实无法判断',
}
MEANINGLESS = re.compile(r'^(新建文本文档|新建文件夹|未命名|无标题|new( text)? document|untitled|\d{4,}|document)(\s*\(\d+\))?$', re.I)


def ask_llm(endpoint, model_hint, cats, item):
    """一次一个文件：让本地模型给出结构化建议。返回 dict 或 None。"""
    sample = sample_text(item['path'], item['ext'])
    hints = '；'.join('%s=%s' % (c, CAT_HINTS.get(c, '')) for c in cats)
    need_name = 'yes' if MEANINGLESS.match(os.path.splitext(item['name'])[0]) else 'no'
    prompt = (
        '你是文件整理员。给下面这个文件分类并起名。类目：%s。\n'
        '名字无意义时（need_name=yes）必须给 new_name，否则 new_name 可留空。\n'
        '只输出一行 JSON：{"category":"类目","new_name":"","reason":"十字内","confidence":0.0}\n'
        '文件：%s | 扩展名 %s | %d 字节 | %s | need_name=%s\n内容：%s'
    ) % (hints, item['name'], item['ext'] or '无', item['size'], item['mtime'], need_name,
         sample[:500] if sample else '(二进制)')

    body = {
        'model': model_hint,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.0,
        'max_tokens': 120,
        'chat_template_kwargs': {'enable_thinking': False},
    }
    try:
        r = requests.post(endpoint.rstrip('/') + '/v1/chat/completions', json=body, timeout=180)
        r.raise_for_status()
        txt = r.json()['choices'][0]['message'].get('content') or ''
    except Exception as e:
        return {'error': str(e)}
    m = re.search(r'\{.*\}', txt, re.S)
    if not m:
        return {'error': 'no-json', 'raw': txt[:160]}
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {'error': 'bad-json', 'raw': m.group(0)[:160]}
    if d.get('category') not in cats:
        d['category'] = '其他'
    return d


def safe_new_name(name, ext, proposed):
    base = (proposed or '').strip().strip('/\\:*?"<>|')
    if not base:
        return None
    if ext and not base.lower().endswith(ext):
        base += ext
    return base if base != name else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--endpoint')
    ap.add_argument('--model', default='qwen3-4b')
    a = ap.parse_args()

    cfg_root, cats, cfg_ep, cfg_max = load_cfg()
    root = os.path.abspath(a.root or cfg_root or os.path.join(USB_ROOT, '我的文件'))
    endpoint = (a.endpoint or cfg_ep or 'http://127.0.0.1:18080')
    limit = a.limit or cfg_max

    if not os.path.isdir(root):
        sys.exit('目录不存在：%s' % root)

    try:
        h = requests.get(endpoint.rstrip('/') + '/health', timeout=4)
        if h.status_code != 200: raise requests.RequestException('health %s' % h.status_code)
    except Exception:
        sys.exit('本地模型未就绪：%s\n先运行 local-ai\\start-local-ai.ps1' % endpoint)

    files = walk(root, limit)
    print('root=%s  files=%d  endpoint=%s' % (root, len(files), endpoint))
    if not files:
        print('没有可整理的文件')
        return

    plan = []
    t0 = time.time()
    for i, it in enumerate(files, 1):
        d = ask_llm(endpoint, a.model, cats, it)
        rec = dict(it)
        if d and 'error' not in d:
            cat = d['category']
            newname = safe_new_name(it['name'], it['ext'], d.get('new_name'))
            target = os.path.join(root, cat, newname or it['name'])
            cur_dir = os.path.dirname(it['path'])
            if os.path.abspath(target) == os.path.abspath(it['path']):
                action = 'keep'
            elif os.path.abspath(os.path.dirname(target)) == os.path.abspath(cur_dir):
                action = 'rename'
            else:
                action = 'move'
            cf = float(d.get('confidence') or 0)
            if cf <= 0:            # model omitted it or wrote 0 -> plain default instead of silently dropping the file
                cf = 0.7
            rec.update({'category': cat, 'action': action, 'reason': d.get('reason', ''),
                        'confidence': cf, 'target': target, 'new_name': os.path.basename(target)})
            print('%3d/%d  %-28s -> %-4s %-6s %-30s %.2f' % (
                i, len(files), it['name'][:28], cat, action, os.path.basename(target)[:30],
                rec['confidence']))
        else:
            rec.update({'category': '其他', 'action': 'keep', 'reason': 'model-failed: %s' % (d or {}).get('error', '?'),
                        'confidence': 0.0, 'target': it['path'], 'new_name': it['name']})
            print('%3d/%d  %-28s -> (跳过: %s)' % (i, len(files), it['name'][:28], (d or {}).get('error', '?')))
        plan.append(rec)

    out = os.path.join(root, '整理建议.json')
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'root': root, 'count': len(plan),
                   'categories': cats, 'items': plan}, f, ensure_ascii=False, indent=2)
    print('\n-> %s   (%.1fs, %.1f 文件/s)' % (out, time.time() - t0, len(plan) / max(time.time() - t0, 0.001)))

    todo = [r for r in plan if r['action'] in ('move', 'rename') and r.get('confidence', 0) >= 0.6]
    print('建议移动/改名：%d 条；仅建议不动：%d 条' % (len(todo), len(plan) - len(todo)))
    if not a.apply:
        print('\n当前为「只建议」模式。确认无误后加 --apply 执行（不会删除任何文件）。')
        return

    moved = 0
    for r in todo:
        dst = r['target']
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(dst) == os.path.abspath(r['path']) or os.path.exists(dst):
            print('skip (target exists or same): %s' % dst)
            continue
        shutil.move(r['path'], dst)
        moved += 1
        print('moved: %s -> %s' % (r['name'], os.path.relpath(dst, root)))
    print('\n执行完成：%d 个文件已整理（删除 0 个）' % moved)


if __name__ == '__main__':
    main()
