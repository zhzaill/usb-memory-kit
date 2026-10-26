# memory-kit

Portable, local-first log memory for Windows.

```text
discover roots → SHA256 archive → chunk → embed → cluster
                                      │
                       ┌──────────────┼──────────────┐
                  智能检索         原始日志          光场
```

## Design

- Original logs remain the source of truth.
- USB storage contains only derived archive and indexes.
- Raw copies remain readable when embeddings are offline.
- Search combines BM25 and embedding similarity with RRF.
- Working memory is owner-scoped and bounded; context packs have a TTL.
- The HTTP server binds to `127.0.0.1` by default.

## Entry points

From the USB root:

```text
控制台.cmd     terminal-style field console: status, sync, archive and launch
吸收日志.cmd   discover + collect + index logs from this machine
启动检索.cmd   start the local web application in portable Firefox
启动本地AI.cmd start optional llama.cpp chat/embedding servers
```

The copied source logs live under `corpus/<COMPUTERNAME>/`. The generated files are
`index/chunks.jsonl` (text chunks), `index/vectors.jsonl` (embeddings) and
`index/organization.json` (communities). A successful full run prints and checks
that vector count equals chunk count before rebuilding communities.

Manual equivalent:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <USB_ROOT>\memory-kit\bin\pipeline.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File <USB_ROOT>\memory-kit\start.ps1
```

## Views

- **智能检索**: hybrid semantic and keyword retrieval.
- **原始日志**: browse, copy and download complete source files.
- **光场**: HALOFLUX Canvas visualization driven by live archive metrics.

Switch views from the top bar. The current query and selected raw log are kept in
the URL and browser history.

## Configuration

- `config/machines.json`: per-machine log roots and explicit files.
- `config/kit.json`: embedding endpoints, chunking, clustering and memory settings.
- `config/categories.json`: file-organizer categories.
- `config/secret.ps1`: optional local tunnel credentials, never committed.

`start.ps1` generates `mcp/memory-kit.resolved.json` for the current drive letter.

### Project anchors

Stable rule or architecture documents can be registered as named roots in the current
machine entry. Anchors collect Markdown only and appear in result sources with an
`anchor-<id>` tag and explicit anchor metadata, separate from chronological work logs:

```json
{
  "id": "workspace-rules",
  "anchor": true,
  "path": "C:\\Projects\\ai-workspace-rules"
}
```

Use a narrow documentation directory when possible; do not point an anchor at a whole
repository containing source code, dependencies or generated output.

## Embedding chain

1. On-stick llama.cpp embedding endpoint.
2. Optional SSH tunnel to a remote GPU endpoint.
3. Keyword-only BM25 fallback.

The archive and raw-log interface do not require an embedding endpoint.

## MCP tools

- `search_memory`
- `recent_logs`
- `clusters`
- `kit_about`
- `create_memory_session`
- `append_memory_turn`
- `session_history`
- `memory_context`
- `get_memory_context`

## Generated directories

`corpus/`, `index/`, `runtime/` and `state/` are generated and ignored by Git.
See the repository-level `USB-LAYOUT.md`, `README.md`, `CREDITS.md` and
`SECURITY.md` for the complete portable layout.
