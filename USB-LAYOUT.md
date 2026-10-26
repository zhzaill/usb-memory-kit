# USB Layout

## Root

| Path | Responsibility |
|---|---|
| `README.md` / `README.txt` | Repository and on-stick instructions |
| `LICENSE` | MIT license for this layout |
| `CREDITS.md` | Attribution and upstream projects |
| `SECURITY.md` | Data and credential boundary |
| `控制台.cmd` / `console.ps1` | Terminal-style operation menu with sync, status and archive shortcuts |
| `吸收日志.cmd` | Copy and index logs from the current machine |
| `启动检索.cmd` | One-click: start the service if needed and open portable Firefox |
| `启动本地AI.cmd` | Start optional local llama.cpp endpoints |
| `我的文件/` | User-controlled files; never committed |

## memory-kit

| Path | Responsibility |
|---|---|
| `bin/collect.ps1` | SHA256-idempotent copy from local roots into `corpus/` |
| `bin/discover-roots.ps1` | Four-layer log-root discovery |
| `bin/pipeline.ps1` | Root discovery → collect → chunk → embed → organize |
| `bin/chunk.py` | Markdown/log/CSV/TXT chunking with encoding fallback |
| `bin/embed.py` | Incremental embedding |
| `bin/organize.py` | kNN graph and Louvain communities |
| `bin/kitcore.py` | Shared hybrid retrieval core |
| `bin/memory_service.py` | Normalized session/context memory gateway |
| `bin/log_archive.py` | Human-readable raw archive API |
| `bin/serve.py` | Local HTTP server and three-view web application |
| `bin/mcp_server.py` | MCP stdio tools |
| `config/kit.json` | Retrieval and runtime parameters |
| `config/machines.json` | Per-machine log root registry |
| `config/categories.json` | File-organizer category set |
| `web/index.html` | Search and raw-log interfaces |
| `web/haloflux.html` | Data-driven HALOFLUX light-field view |
| `web/HALOFLUX-LICENSE.txt` | Upstream MIT license |
| `corpus/` | Generated raw archive; ignored by Git |
| `index/` | Generated chunks, vectors and communities; ignored by Git |
| `runtime/` | Generated Python environment and caches; ignored by Git |
| `state/` | Working-memory sessions and runtime state; ignored by Git |

## local-ai

| Path | Responsibility |
|---|---|
| `start-local-ai.ps1` | Starts chat and embedding llama.cpp servers |
| `启动本地AI.cmd` | Double-click launcher |
| `models/` | GGUF model files; ignored by Git |
| `llama/` | Vulkan llama.cpp build; ignored by Git |
| `llama-cpu/` | CPU llama.cpp fallback; ignored by Git |
| `_dl/` | Optional archive downloads; ignored by Git |
| `state/` | Process IDs and logs; ignored by Git |

## Generated data

The archive, vector index and working-memory sessions are products of a specific
machine and should not be published by default. Back them up separately when needed.
