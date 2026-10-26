#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-kit :: serve.py —— 内存混合检索 HTTP 服务（人用）
GET /api/health  /api/search?q=&k=&mode=&machine=&from=&to=&topic=
GET /api/clusters  /api/chunk?id=   GET / 极简前端
POST/GET/DELETE /api/sessions, /api/sessions/{id}, /api/sessions/{id}/turns
POST /api/context, GET /api/context/{id}
UI 按 Primer 设计系统（浅色、token 化、无阴影/渐变）呈现 Google 搜索页式布局。
导航：搜索用 pushState 入历史，浏览器前进/后退与顶栏品牌"回首页"均可用。
"""
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kitcore import KitIndex, KIT  # noqa: E402
from memory_service import (  # noqa: E402
    MemoryNotFound,
    MemoryProtocolError,
    MemoryService,
)
from log_archive import LogArchive  # noqa: E402

INDEX = KitIndex().load()
SERVICE = MemoryService(INDEX, KIT, INDEX.cfg)
ARCHIVE = LogArchive(
    os.path.join(KIT, 'corpus'),
    INDEX.cfg.get('chunk', {}).get('extensions', ['.md', '.log', '.csv', '.txt']),
)
PAGE_PATH = os.path.join(KIT, 'web', 'index.html')
HALOFLUX_PATH = os.path.join(KIT, 'web', 'haloflux.html')

PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>memory-kit</title>
<style>
:root{
 --p-canvas:#FFFFFF; --p-subtle:#F6F8FA; --p-border:#D1D9E0;
 --p-fg:#1F2328; --p-muted:#59636E; --p-faint:#6E7781;
 --p-accent:#0969DA; --p-accent-subtle:#DDF4FF;
 --p-attention:#9A6700;
 --p-mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--p-canvas);color:var(--p-fg);
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans","Microsoft YaHei",sans-serif;
 font-size:14px;line-height:1.55}
a{color:var(--p-accent);text-decoration:none}
a:hover{text-decoration:underline}
.mono{font-family:var(--p-mono)}
button{font:inherit;cursor:pointer}
:focus-visible{outline:2px solid var(--p-accent);outline-offset:1px}
/* ---- 落地页 ---- */
#landing{min-height:92vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px}
.brand{font-size:34px;font-weight:600;letter-spacing:-.5px;margin:0 0 6px}
.brand i{font-style:normal;color:var(--p-accent)}
.tagline{color:var(--p-muted);margin-bottom:28px}
.searchbar{display:flex;width:min(600px,92vw);border:1px solid var(--p-border);border-radius:6px;background:var(--p-canvas)}
.searchbar:focus-within{border-color:var(--p-accent)}
.searchbar input{flex:1;border:0;outline:0;padding:10px 12px;font-size:15px;background:transparent;color:var(--p-fg);min-width:0}
.searchbar>svg{align-self:center;margin:0 10px;flex:none;color:var(--p-muted)}
.searchbar button{border:0;background:transparent;display:flex;align-items:center;padding:0 12px;
 color:var(--p-muted);border-radius:0 5px 5px 0}
.searchbar button:hover{background:var(--p-subtle);color:var(--p-accent)}
.searchbar button svg{margin:0}
.chips{margin-top:28px;display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:760px}
.chip{background:var(--p-subtle);border:1px solid var(--p-border);border-radius:10px;padding:3px 10px;
 font-size:12px;color:var(--p-muted)}
.chip:hover{border-color:var(--p-accent);color:var(--p-accent)}
.hint{margin-top:24px;color:var(--p-faint);font-size:12px}
/* ---- 结果页 ---- */
#app{display:none;min-height:100vh;flex-direction:column}
header{position:sticky;top:0;background:var(--p-canvas);border-bottom:1px solid var(--p-border);
 padding:8px 20px;display:flex;gap:16px;align-items:center;z-index:2}
.brand-sm{font-size:18px;font-weight:600;white-space:nowrap;color:var(--p-fg)}
.brand-sm i{font-style:normal;color:var(--p-accent)}
header .searchbar{flex:1;width:min(640px,60vw)}
select{border:1px solid var(--p-border);border-radius:6px;background:var(--p-subtle);color:var(--p-fg);
 padding:6px 8px;font-size:13px}
main{display:flex;gap:24px;padding:16px 20px;flex:1;max-width:1200px;margin:0 auto;width:100%}
#rail{width:224px;flex:none}
#rail h3{font-size:12px;font-weight:600;color:var(--p-muted);margin:4px 0 8px;
 text-transform:uppercase;letter-spacing:.04em}
.citem{display:block;width:100%;text-align:left;background:none;border:0;border-radius:6px;
 padding:4px 8px;font-size:12px;color:var(--p-muted);
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.citem:hover{background:var(--p-accent-subtle);color:var(--p-accent)}
#results{flex:1;min-width:0}
#meta{color:var(--p-muted);font-size:12px;padding:2px 0 12px;border-bottom:1px solid var(--p-border)}
.res{padding:14px 0;border-bottom:1px solid var(--p-border)}
.res h2{margin:0;font-size:16px;font-weight:600}
.meta{font-size:12px;color:var(--p-faint);margin:2px 0 6px;font-family:var(--p-mono)}
.pv{font-size:14px;color:var(--p-muted)}
.full{background:var(--p-subtle);border:1px solid var(--p-border);border-radius:6px;margin-top:8px;padding:8px 12px}
.full .fh{font-family:var(--p-mono);font-size:12px;color:var(--p-faint)}
.full pre{white-space:pre-wrap;font-family:inherit;font-size:13px;margin:4px 0 0;color:var(--p-fg)}
.warn{color:var(--p-attention);background:var(--p-subtle);border:1px solid var(--p-border);
 border-radius:6px;padding:8px 12px;font-size:13px;margin-bottom:12px}
footer{border-top:1px solid var(--p-border);background:var(--p-subtle);padding:4px 20px;
 font-size:12px;color:var(--p-faint);font-family:var(--p-mono)}
footer span+span{margin-left:16px}
@media(max-width:900px){#rail{display:none}}
</style></head><body>

<div id="landing">
 <h1 class="brand">memory<i>&middot;</i>kit</h1>
 <div class="tagline" id="tg">随身日志记忆库</div>
 <form class="searchbar" id="f0">
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215ZM11.5 7a4.5 4.5 0 1 0-9 0 4.5 4.5 0 0 0 9 0Z"/></svg>
  <input id="q0" type="text" placeholder="搜索全部日志记忆…" aria-label="搜索记忆库" autofocus>
  <button type="submit" aria-label="搜索" title="检索"><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215ZM11.5 7a4.5 4.5 0 1 0-9 0 4.5 4.5 0 0 0 9 0Z"/></svg></button>
 </form>
 <div class="chips" id="chips"></div>
 <div class="hint">回车检索 &middot; hybrid = 语义+关键词融合 &middot; 浏览器后退可回首页</div>
</div>

<div id="app">
 <header>
  <a class="brand-sm" id="home" href="./" title="返回首页">memory<i>&middot;</i>kit</a>
  <form class="searchbar" id="f1">
   <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215ZM11.5 7a4.5 4.5 0 1 0-9 0 4.5 4.5 0 0 0 9 0Z"/></svg>
   <input id="q" type="text" aria-label="搜索记忆库">
   <button type="submit" aria-label="搜索" title="检索"><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215ZM11.5 7a4.5 4.5 0 1 0-9 0 4.5 4.5 0 0 0 9 0Z"/></svg></button>
  </form>
  <select id="mode" aria-label="检索模式" title="hybrid=语义+关键词，dense=纯语义，sparse=纯关键词">
   <option value="hybrid">hybrid</option><option value="dense">dense</option><option value="sparse">sparse</option>
  </select>
 </header>
 <main>
  <nav id="rail" aria-label="社区导航"><h3>社区</h3><div id="clist"></div></nav>
  <section id="results">
   <div id="meta" class="mono"></div>
   <div id="rlist"></div>
  </section>
 </main>
 <footer id="foot"></footer>
</div>

<script>
let CL=[];
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')}
function setView(app){
  document.getElementById('landing').style.display = app ? 'none' : 'flex';
  document.getElementById('app').style.display = app ? 'flex' : 'none';
}
function goHome(push){
  document.getElementById('q0').value='';
  setView(false);
  if(push) history.pushState({}, '', location.pathname);
  document.getElementById('q0').focus();
}
async function init(){
 const h=await (await fetch('/api/health')).json();
 const c=await (await fetch('/api/clusters')).json();
 CL=c.clusters||[];
 document.getElementById('tg').textContent='随身日志记忆库 · '+h.chunks+' 块 · '+h.vectors+' 向量 · '+(c.stats?c.stats.communities:'?')+' 社区';
 const chips=document.getElementById('chips');
 CL.slice(0,12).forEach(x=>{
   const b=document.createElement('button');b.type='button';b.className='chip';
   b.textContent='#'+x.id+' '+(x.topics[0]||'')+' ('+x.size+')';
   b.title='社区 #'+x.id+'：'+(x.topics||[]).join(' / ');
   b.onclick=()=>{document.getElementById('q0').value=x.topics[0]||'';landGo();};
   chips.appendChild(b);});
 const clist=document.getElementById('clist');
 CL.slice(0,30).forEach(x=>{
   const d=document.createElement('button');d.type='button';d.className='citem';
   d.textContent='#'+x.id+' · '+x.size+' · '+(x.topics[0]||'');
   d.title=(x.topics||[]).join(' / ')+'  '+(x.from||'')+'..'+(x.to||'');
   d.onclick=()=>{document.getElementById('q').value=x.topics[0]||'';go2(true);};
   clist.appendChild(d);});
 document.getElementById('foot').innerHTML=
  '<span>'+esc(h.embed_endpoint||'no endpoint')+'</span><span>kit '+esc(h.kit_root)+'</span>';
 document.getElementById('home').addEventListener('click',e=>{e.preventDefault();goHome(true);});
 const qp=new URLSearchParams(location.search).get('q');
 if(qp){document.getElementById('q').value=qp;setView(true);go2(false);}
}
function landGo(){
 const q=document.getElementById('q0').value.trim();if(!q)return;
 document.getElementById('q').value=q;
 setView(true);
 document.getElementById('q').focus();
 go2(true);
}
async function go2(push){
 const q=document.getElementById('q').value.trim();if(!q)return;
 const mode=document.getElementById('mode').value;
 if(push) history.pushState({q:q}, '', '?q='+encodeURIComponent(q));
 const t0=performance.now();
 const r=await (await fetch('/api/search?q='+encodeURIComponent(q)+'&mode='+mode+'&k=10')).json();
 const ms=(performance.now()-t0).toFixed(0);
 document.getElementById('meta').textContent=
  (r.results.length?r.results.length+' 条结果':'无结果')+' · '+ms+' ms · mode='+mode+
  (r.degraded?' · 已降级 sparse':' · endpoint ok');
 document.getElementById('rlist').innerHTML=
  (r.degraded?'<div class="warn" role="alert">embedding 端点不可用，本次为纯关键词检索</div>':'')+
  r.results.map(x=>
   '<div class="res"><h2><a href="#" class="chunk-link" data-id="'+x.id+'" title="点击展开/收起全文">'+esc(x.topic)+'</a></h2>'+
   '<div class="meta">'+(x.date||'undated')+' · '+(x.machines||[]).join(',')+' · cluster#'+x.cluster+
   ' · '+(x.score_norm*100).toFixed(1)+'% · d '+(x.dense===null?'—':x.dense)+' / b '+(x.bm25===null?'—':x.bm25)+
   ' · '+esc(x.source)+'</div>'+
   '<div class="pv">'+esc(x.preview)+'…</div></div>').join('');
}
window.addEventListener('popstate',()=>{
 const q=new URLSearchParams(location.search).get('q');
 if(q){document.getElementById('q').value=q;setView(true);go2(false);}
 else goHome(false);
});
document.getElementById('rlist').addEventListener('click',async e=>{
 const a=e.target.closest('a.chunk-link');if(!a)return;
 e.preventDefault();
 const id=a.dataset.id;
 const old=document.getElementById('full-'+id);
 if(old){old.remove();return;}
 const m=await (await fetch('/api/chunk?id='+encodeURIComponent(id))).json();
 if(!m||m.error)return;
 const div=document.createElement('div');div.className='full';div.id='full-'+id;
 const fh=document.createElement('div');fh.className='fh';fh.textContent=(m.headings||[]).join(' > ');
 const pre=document.createElement('pre');pre.textContent=m.text;
 div.appendChild(fh);div.appendChild(pre);
 a.closest('.res').appendChild(div);
});
document.getElementById('f0').addEventListener('submit',e=>{e.preventDefault();landGo();});
document.getElementById('f1').addEventListener('submit',e=>{e.preventDefault();go2(true);});
// keydown 兜底：个别内嵌 webview 不触发表单隐式提交
document.getElementById('q0').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();landGo();}});
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();go2(true);}});
init();
</script></body></html>"""


def sync_logs():
    script = os.path.join(KIT, 'bin', 'collect.ps1')
    system_root = os.environ.get('SystemRoot', r'C:\Windows')
    shell = os.path.join(
        system_root, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
    if not os.path.isfile(shell):
        shell = shutil.which('powershell') or shutil.which('powershell.exe')
    if not shell:
        raise RuntimeError('PowerShell not found')
    env = dict(os.environ)
    # The Codex runtime can prepend PowerShell Core modules. Windows PowerShell
    # 5.1 must load its own Utility module or Get-FileHash is unavailable.
    env['PSModulePath'] = ';'.join([
        os.path.join(os.environ.get('USERPROFILE', ''), 'Documents', 'WindowsPowerShell', 'Modules'),
        os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'WindowsPowerShell', 'Modules'),
        os.path.join(system_root, 'System32', 'WindowsPowerShell', 'v1.0', 'Modules'),
    ])
    proc = subprocess.run(
        [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script],
        cwd=KIT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
    )
    raw = proc.stdout or b''
    try:
        output = raw.decode('utf-8')
    except UnicodeDecodeError:
        output = raw.decode('gb18030', errors='replace')
    return proc.returncode, output.strip()


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, body, content_type, code=200, headers=None):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _page(self):
        if os.path.isfile(PAGE_PATH):
            with open(PAGE_PATH, 'rb') as handle:
                return handle.read()
        return PAGE.encode('utf-8')

    def _error(self, exc):
        if isinstance(exc, (MemoryNotFound, FileNotFoundError)):
            self._json({'error': str(exc)}, 404)
        elif isinstance(exc, (MemoryProtocolError, ValueError)):
            self._json({'error': str(exc)}, 400)
        else:
            self._json({'error': 'internal error'}, 500)

    def _read_json(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise MemoryProtocolError('invalid Content-Length')
        if length <= 0 or length > 1024 * 1024:
            raise MemoryProtocolError('JSON body must be between 1 byte and 1 MiB')
        try:
            value = json.loads(self.rfile.read(length).decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            raise MemoryProtocolError('invalid JSON body')
        if not isinstance(value, dict):
            raise MemoryProtocolError('JSON body must be an object')
        return value

    def _path(self, raw):
        path = urlparse(raw).path
        if path == '/v1/memory' or path.startswith('/v1/memory/'):
            path = '/api' + path[len('/v1/memory'):]
        return path.rstrip('/') or '/'

    def do_GET(self):
        u = urlparse(self.path)
        p = self._path(self.path)
        q = {kk: vv[0] for kk, vv in parse_qs(u.query).items()}
        try:
            if p == '/' or p == '/index.html':
                body = self._page()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
            elif p == '/api/health':
                self._json({
                    'status': 'ok', 'chunks': len(INDEX.chunks), 'vectors': INDEX.n,
                    'embed_endpoint': INDEX.cfg.get('embed', {}).get('endpoints', [{}])[0].get('url'),
                    'kit_root': KIT, 'memory': SERVICE.stats(),
                })
            elif p in ('/haloflux', '/haloflux.html'):
                with open(HALOFLUX_PATH, 'rb') as handle:
                    body = handle.read()
                self._bytes(body, 'text/html; charset=utf-8')
            elif p == '/api/search':
                self._json(SERVICE.search(q, protocol='http'))
            elif p == '/api/clusters':
                self._json(INDEX.cluster_info() or {'clusters': []})
            elif p == '/api/recent':
                self._json({'results': INDEX.recent(int(q.get('days', 3)), int(q.get('k', 20)))})
            elif p == '/api/chunk':
                m = INDEX.by_id.get(q.get('id', ''))
                self._json(m if m else {'error': 'not found'}, 200 if m else 404)
            elif p == '/api/logs':
                self._json(ARCHIVE.list(
                    query=q.get('q', ''),
                    extension=q.get('ext', ''),
                    limit=int(q.get('limit', 500)),
                ))
            elif p == '/api/logs.zip':
                body = ARCHIVE.zip_bytes()
                self._bytes(
                    body,
                    'application/zip',
                    headers={'Content-Disposition': 'attachment; filename="memory-kit-logs.zip"'},
                )
            elif p == '/api/log/download':
                path = ARCHIVE.path_for(q.get('id', ''))
                with open(path, 'rb') as handle:
                    body = handle.read()
                filename = quote(os.path.basename(path), safe='')
                self._bytes(
                    body,
                    mimetypes.guess_type(path)[0] or 'application/octet-stream',
                    headers={
                        'Content-Disposition':
                            'attachment; filename="log.txt"; filename*=UTF-8\'\'%s' % filename
                    },
                )
            elif p == '/api/log':
                self._json(ARCHIVE.get(q.get('id', '')))
            elif p == '/api/sessions':
                items = SERVICE.list_sessions(q.get('owner'), int(q.get('limit', 50)))
                self._json({'object': 'memory.sessions', 'results': items})
            elif p.startswith('/api/sessions/'):
                sid = unquote(p[len('/api/sessions/'):])
                item = SERVICE.get_session(q.get('owner'), sid)
                self._json({'object': 'memory.session', 'session': item})
            elif p.startswith('/api/context/'):
                cid = unquote(p[len('/api/context/'):])
                self._json(SERVICE.get_context(q.get('owner'), cid))
            else:
                self._json({'error': 'no such route'}, 404)
        except (MemoryProtocolError, MemoryNotFound, FileNotFoundError, ValueError) as exc:
            self._error(exc)

    def do_POST(self):
        p = self._path(self.path)
        try:
            body = self._read_json()
            if p == '/api/search':
                self._json(SERVICE.search(body, protocol='http'))
            elif p == '/api/sessions':
                item = SERVICE.create_session(body)
                self._json({'object': 'memory.session', 'session': item}, 201)
            elif p.startswith('/api/sessions/') and p.endswith('/turns'):
                sid = unquote(p[len('/api/sessions/'):-len('/turns')])
                owner = body.get('owner')
                item = SERVICE.append_turn(owner, sid, body)
                self._json({'object': 'memory.session', 'session': item})
            elif p == '/api/context':
                self._json(SERVICE.build_context(body), 201)
            elif p == '/api/logs/sync':
                code, output = sync_logs()
                stats = ARCHIVE.list()['stats']
                self._json({
                    'success': code == 0,
                    'exit_code': code,
                    'output': output,
                    'stats': stats,
                }, 200 if code == 0 else 500)
            else:
                self._json({'error': 'no such route'}, 404)
        except (
            MemoryProtocolError, MemoryNotFound, FileNotFoundError,
            ValueError, RuntimeError, subprocess.TimeoutExpired,
        ) as exc:
            self._error(exc)

    def do_DELETE(self):
        u = urlparse(self.path)
        p = self._path(self.path)
        q = {kk: vv[0] for kk, vv in parse_qs(u.query).items()}
        try:
            if p.startswith('/api/sessions/'):
                sid = unquote(p[len('/api/sessions/'):])
                SERVICE.delete_session(q.get('owner'), sid)
                self._json({'object': 'memory.session.deleted', 'id': sid})
            else:
                self._json({'error': 'no such route'}, 404)
        except (MemoryProtocolError, MemoryNotFound, FileNotFoundError, ValueError) as exc:
            self._error(exc)


class _V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6


if __name__ == '__main__':
    port = int((INDEX.cfg.get('search', {}) or {}).get('port', 18200))
    # Loopback only, but on both families: some browsers resolve "localhost" to ::1 first and
    # an IPv4-only listener makes the page look unreachable even though 127.0.0.1 works.
    print('memory-kit serving on http://127.0.0.1:%d  (Ctrl+C 停止)' % port)
    server = ThreadingHTTPServer(('127.0.0.1', port), H)
    try:
        v6 = _V6Server(('::1', port), H)
        import threading
        threading.Thread(target=v6.serve_forever, daemon=True).start()
        print('also listening on http://[::1]:%d  (localhost)' % port)
    except OSError as exc:
        print('ipv6 loopback not bound: %s' % exc)
    server.serve_forever()
