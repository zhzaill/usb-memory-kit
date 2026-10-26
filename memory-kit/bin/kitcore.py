#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-kit :: kitcore.py —— 内存索引核心（serve.py 与 mcp_server.py 共用）
全部数据常驻内存：chunks 元数据 + 向量矩阵 + BM25 索引 + 社区归属。
检索语义沿用 2026-10-18 vector-weave 基准验证过的混合方案：
dense(余弦) + sparse(BM25) -> RRF 融合；embedding 端点缺席时自动降级 sparse。
"""
import json
import os
import re
import sys
import time

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CJK_RE = re.compile(r'[\u4e00-\u9fff]')
ASCII_TOKEN_RE = re.compile(r'[A-Za-z0-9_\-./\\]{2,}')


def tokenize(text):
    """中文连续段切 bigram，英文/数字/路径切 >=2 长 token（与 vector-weave 一致）。"""
    toks = []
    for m in ASCII_TOKEN_RE.finditer(text):
        toks.append(m.group(0).lower())
    # 逐字符扫描中文段做 bigram
    buf = []
    for ch in text:
        if CJK_RE.match(ch):
            buf.append(ch)
        else:
            if len(buf) >= 2:
                for i in range(len(buf) - 1):
                    toks.append(buf[i] + buf[i + 1])
            elif len(buf) == 1:
                toks.append(buf[0])
            buf = []
    if len(buf) >= 2:
        for i in range(len(buf) - 1):
            toks.append(buf[i] + buf[i + 1])
    elif len(buf) == 1:
        toks.append(buf[0])
    return toks


def _cfg():
    return json.load(open(os.path.join(KIT, 'config', 'kit.json'), encoding='utf-8'))


class KitIndex:
    def __init__(self):
        self.cfg = _cfg()
        self.chunks = []
        self.by_id = {}
        self.ids = []
        self.M = None            # (n, dim) L2 归一化
        self.bm25 = None
        self.org = None
        self.cluster_of = {}     # chunk id -> cluster id
        self.n = 0

    # ---- 装载 ----
    def load(self):
        t0 = time.time()
        idx = os.path.join(KIT, 'index')
        self.chunks = [json.loads(l) for l in open(os.path.join(idx, 'chunks.jsonl'), encoding='utf-8') if l.strip()]
        self.by_id = {c['id']: c for c in self.chunks}
        vecs = {}
        for l in open(os.path.join(idx, 'vectors.jsonl'), encoding='utf-8'):
            if l.strip():
                rec = json.loads(l)
                vecs[rec['id']] = rec['vector']
        self.ids = [c['id'] for c in self.chunks if c['id'] in vecs]
        M = np.array([vecs[i] for i in self.ids], dtype=np.float32) if self.ids else np.zeros((0, 1), np.float32)
        if len(M):
            M /= (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
        self.M = M
        self.n = len(self.ids)
        self.pos = {cid: i for i, cid in enumerate(self.ids)}

        from rank_bm25 import BM25Okapi
        corpus = [tokenize(self.by_id[cid]['embed_text']) for cid in self.ids]
        self.bm25 = BM25Okapi(corpus) if corpus and any(corpus) else None

        org_path = os.path.join(idx, 'organization.json')
        if os.path.exists(org_path):
            self.org = json.load(open(org_path, encoding='utf-8'))
            for cl in self.org.get('clusters', []):
                for mid in cl.get('members', []):
                    self.cluster_of[mid] = cl['id']
        print('[kitcore] loaded chunks=%d vectors=%d clusters=%s in %.1fs' % (
            len(self.chunks), self.n,
            len(self.org['clusters']) if self.org else 0, time.time() - t0),
            file=sys.stderr)
        return self

    # ---- embedding 端点 ----
    def embed_query(self, text):
        import requests
        for ep in self.cfg.get('embed', {}).get('endpoints', []):
            try:
                r = requests.post(ep['url'], json={'input': [text], 'model': ep.get('model', '')}, timeout=30)
                if r.status_code == 200:
                    v = np.array(r.json()['data'][0]['embedding'], dtype=np.float32)
                    return v / (np.linalg.norm(v) + 1e-9)
            except requests.RequestException:
                continue
        return None

    # ---- 检索 ----
    def search(self, q, k=None, mode='hybrid', machine=None, date_from=None, date_to=None, topic=None):
        k = k or int(self.cfg.get('search', {}).get('default_k', 10))
        rrf_k = int(self.cfg.get('search', {}).get('rrf_k', 60))
        metas = [self.by_id[cid] for cid in self.ids]
        mask = []
        for m in metas:
            ok = True
            if machine and machine.lower() not in [x.lower() for x in m['machines']]:
                ok = False
            if date_from and (not m['date'] or m['date'] < date_from):
                ok = False
            if date_to and (not m['date'] or m['date'] > date_to):
                ok = False
            if topic and topic.lower() not in m['topic'].lower():
                ok = False
            mask.append(ok)
        mask = np.array(mask, dtype=bool)
        if not mask.any():
            return {'query': q, 'results': [], 'note': 'no chunk passes filters'}

        qv = self.embed_query(q) if mode in ('hybrid', 'dense') else None
        degraded = mode == 'hybrid' and qv is None

        dense_rank = {}
        sparse_rank = {}
        if qv is not None:
            scores = self.M @ qv
            scores[~mask] = -np.inf
            order = np.argsort(-scores)
            for rank, i in enumerate(order[:200]):
                if not np.isfinite(scores[i]):
                    break
                dense_rank[self.ids[i]] = (rank, float(scores[i]))
        if self.bm25 is not None and mode in ('hybrid', 'sparse') or degraded:
            bs = np.array(self.bm25.get_scores(tokenize(q))) if self.bm25 is not None else np.zeros(self.n)
            bs[~mask] = -np.inf
            if np.isfinite(bs).any() and bs.max() > 0:
                order = np.argsort(-bs)
                for rank, i in enumerate(order[:200]):
                    if not np.isfinite(bs[i]) or bs[i] <= 0:
                        break
                    sparse_rank[self.ids[i]] = (rank, float(bs[i]))

        fused = {}
        for cid in set(dense_rank) | set(sparse_rank):
            s = 0.0
            if cid in dense_rank:
                s += 1.0 / (rrf_k + dense_rank[cid][0])
            if cid in sparse_rank:
                s += 1.0 / (rrf_k + sparse_rank[cid][0])
            fused[cid] = s
        top = sorted(fused.items(), key=lambda x: -x[1])[:k]
        results = []
        first = top[0][1] if top else 1.0
        for cid, s in top:
            m = self.by_id[cid]
            results.append({
                'score': round(s, 6),
                'score_norm': round(s / first, 4) if first else 0,
                'dense': round(dense_rank[cid][1], 4) if cid in dense_rank else None,
                'bm25': round(sparse_rank[cid][1], 4) if cid in sparse_rank else None,
                'cluster': self.cluster_of.get(cid),
                'id': cid,
                'topic': m['topic'],
                'date': m['date'],
                'machines': m['machines'],
                'source': m['source'],
                'anchor': m.get('anchor'),
                'headings': m['headings'],
                'preview': m['text'][:200],
                'chars': m['chars'],
            })
        return {'query': q, 'mode': mode, 'degraded': degraded, 'k': k, 'results': results}

    def cluster_info(self):
        if not self.org:
            return None
        return {
            'generated_at': self.org.get('generated_at'),
            'params': self.org.get('params'),
            'stats': self.org.get('stats'),
            'clusters': [
                {kk: c[kk] for kk in ('id', 'size', 'topics', 'keywords', 'from', 'to', 'machines')}
                for c in self.org.get('clusters', [])
            ],
        }

    def recent(self, days=3, k=20):
        import datetime
        today = datetime.date.today()
        lo = (today - datetime.timedelta(days=days)).isoformat()
        out = []
        for m in self.chunks:
            if m['date'] and m['date'] >= lo:
                out.append(m)
        out.sort(key=lambda x: (x['date'], x['source']), reverse=True)
        return [{'id': m['id'], 'date': m['date'], 'topic': m['topic'],
                 'source': m['source'], 'chars': m['chars'], 'preview': m['text'][:120]} for m in out[:k]]
