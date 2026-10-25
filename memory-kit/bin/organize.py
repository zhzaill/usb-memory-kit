#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-kit :: organize.py —— 内存计算自动整理
把全部向量一次性载入内存：L2 归一化 -> 余弦 kNN 建图 -> Louvain 社区聚类
-> 每个社区聚合主题/关键词/日期范围 -> index/organization.json。
全部计算在 RAM 中完成（numpy 矩阵运算 + networkx），无数据库、无落盘中间态。
"""
import json
import os
import re
import sys
import time
from collections import Counter

import networkx as nx
import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(KIT, 'index')
CFG = json.load(open(os.path.join(KIT, 'config', 'kit.json'), encoding='utf-8'))

try:
    import jieba
    jieba.initialize()

    def keywords(texts, topn=12):
        cnt = Counter()
        for t in texts:
            for w in jieba.lcut(re.sub(r'\s+', '', t)):
                if len(w) >= 2 and not re.match(r'^[\W\d_]+$', w):
                    cnt[w] += 1
        return [w for w, _ in cnt.most_common(topn)]
except ImportError:
    def keywords(texts, topn=12):
        cnt = Counter()

        def bigrams(s):
            s = re.sub(r'\s+', '', s)
            return [s[i:i + 2] for i in range(len(s) - 1)]
        for t in texts:
            cnt.update(bigrams(t))
        return [w for w, _ in cnt.most_common(topn)]


def load():
    chunks = [json.loads(l) for l in open(os.path.join(INDEX, 'chunks.jsonl'), encoding='utf-8') if l.strip()]
    vecs = {}
    for l in open(os.path.join(INDEX, 'vectors.jsonl'), encoding='utf-8'):
        if l.strip():
            rec = json.loads(l)
            vecs[rec['id']] = rec['vector']
    ids = [c['id'] for c in chunks if c['id'] in vecs]
    by_id = {c['id']: c for c in chunks}
    M = np.array([vecs[i] for i in ids], dtype=np.float32)
    M /= (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    return ids, by_id, M


def main():
    t0 = time.time()
    org_cfg = CFG.get('organize', {})
    k = int(org_cfg.get('k', 8))
    thr = float(org_cfg.get('threshold', 0.55))
    res = float(org_cfg.get('resolution', 1.0))
    seed = int(org_cfg.get('seed', 42))

    ids, by_id, M = load()
    n = len(ids)
    if n == 0:
        sys.exit('没有可用向量，先运行 embed.py')
    print('loaded %d vectors dim=%d (%.1fs)' % (n, M.shape[1], time.time() - t0))

    # 全内存余弦相似度矩阵
    t1 = time.time()
    sim = M @ M.T
    np.fill_diagonal(sim, -1.0)
    G = nx.Graph()
    G.add_nodes_from(range(n))
    order = np.argsort(-sim, axis=1)[:, :k]
    edges = set()
    for i in range(n):
        for j in order[i]:
            if sim[i, j] >= thr:
                edges.add(tuple(sorted((i, j))))
    G.add_edges_from(edges)
    print('knn graph: %d nodes %d edges (%.1fs)' % (n, G.number_of_edges(), time.time() - t1))

    t2 = time.time()
    communities = nx.algorithms.community.louvain_communities(G, weight=None, resolution=res, seed=seed)
    communities = sorted(communities, key=len, reverse=True)
    print('louvain: %d communities (%.1fs)' % (len(communities), time.time() - t2))

    clusters = []
    for ci, members in enumerate(communities):
        mem_ids = [ids[i] for i in sorted(members)]
        meta = [by_id[m] for m in mem_ids]
        topics = Counter(x['topic'] for x in meta if x['topic'])
        dates = sorted({x['date'] for x in meta if x['date']})
        clusters.append({
            'id': ci,
            'size': len(mem_ids),
            'topics': [t for t, _ in topics.most_common(5)],
            'keywords': keywords([x['text'] for x in meta]),
            'from': dates[0] if dates else None,
            'to': dates[-1] if dates else None,
            'machines': sorted({m for x in meta for m in x['machines']}),
            'members': mem_ids,
        })

    out = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'params': {'k': k, 'threshold': thr, 'resolution': res, 'seed': seed, 'dim': int(M.shape[1])},
        'stats': {
            'chunks': n,
            'edges': G.number_of_edges(),
            'communities': len(clusters),
            'degree_mean': round(sum(dict(G.degree()).values()) / max(n, 1), 2),
        },
        'clusters': clusters,
    }
    path = os.path.join(INDEX, 'organization.json')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('-> %s' % path)
    print('top clusters:')
    for c in clusters[:8]:
        print('  #%-3d size=%-4d %s .. %s  %s' % (
            c['id'], c['size'], c['from'] or '?', c['to'] or '?', ' / '.join(c['topics'][:3])))
    print('total %.1fs (all in RAM)' % (time.time() - t0))


if __name__ == '__main__':
    main()
