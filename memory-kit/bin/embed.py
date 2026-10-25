#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-kit :: embed.py
读取 index/chunks.jsonl，把 embed_text 批量发送到 kit.json 配置的 embedding 端点
（优先级从上到下探测，健康检查通过即用），增量写入 index/vectors.jsonl。
用法: python embed.py [--force]  （--force 忽略旧向量全量重算）
"""
import json
import os
import sys
import time

import requests

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(KIT, 'index')
CFG = json.load(open(os.path.join(KIT, 'config', 'kit.json'), encoding='utf-8'))['embed']


def pick_endpoint():
    for ep in CFG.get('endpoints', []):
        try:
            r = requests.get(ep.get('health', ep['url']), timeout=4)
            if r.status_code == 200:
                return ep
        except requests.RequestException:
            continue
    return None


def embed_texts(ep, texts):
    r = requests.post(ep['url'], json={'input': texts, 'model': ep.get('model', '')}, timeout=120)
    r.raise_for_status()
    data = sorted(r.json()['data'], key=lambda d: d.get('index', 0))
    return [d['embedding'] for d in data]


def main():
    force = '--force' in sys.argv
    chunks_path = os.path.join(INDEX, 'chunks.jsonl')
    if not os.path.exists(chunks_path):
        sys.exit('index/chunks.jsonl 不存在，先运行 chunk.py')
    chunks = [json.loads(l) for l in open(chunks_path, encoding='utf-8') if l.strip()]
    vec_path = os.path.join(INDEX, 'vectors.jsonl')
    old = {}
    if os.path.exists(vec_path) and not force:
        for l in open(vec_path, encoding='utf-8'):
            if l.strip():
                rec = json.loads(l)
                old[rec['id']] = rec['vector']

    todo = [c for c in chunks if c['id'] not in old]
    print('chunks=%d cached=%d todo=%d' % (len(chunks), len(chunks) - len(todo), len(todo)))
    if not todo:
        print('nothing to do')
        return

    ep = pick_endpoint()
    if ep is None:
        sys.exit('没有可用 embedding 端点：检查 kit.json endpoints（隧道是否在跑：start.ps1 tunnel）')
    print('endpoint: %s (%s)' % (ep['url'], ep.get('note', '')))

    batch = int(CFG.get('batch', 32))
    t0 = time.time()
    done = 0
    tmp = vec_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        # 先写新算的
        for i in range(0, len(todo), batch):
            part = todo[i:i + batch]
            vecs = embed_texts(ep, [c['embed_text'] for c in part])
            for c, v in zip(part, vecs):
                f.write(json.dumps({'id': c['id'], 'vector': v}, ensure_ascii=False) + '\n')
            done += len(part)
            if done % (batch * 10) == 0 or done == len(todo):
                el = time.time() - t0
                print('embedded %d/%d  %.1fs  %.1f chunks/s' % (done, len(todo), el, done / max(el, 0.001)))
        # 再写仍然被引用的旧向量（清理孤儿）
        cur_ids = {c['id'] for c in chunks}
        for vid, v in old.items():
            if vid in cur_ids:
                f.write(json.dumps({'id': vid, 'vector': v}, ensure_ascii=False) + '\n')
    os.replace(tmp, vec_path)
    print('-> %s  total_vectors=%d  elapsed=%.1fs' % (vec_path, len(cur_ids), time.time() - t0))


if __name__ == '__main__':
    main()
