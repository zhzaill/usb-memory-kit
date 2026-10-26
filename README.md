# USB Memory Kit

A sanitized, drive-letter-independent layout for a portable Windows log memory stick.

> This repository contains the layout and code, not personal logs, indexes, models,
runtime environments, credentials, or user files.

## What it does

1. Finds Markdown and selected text logs on the current Windows machine.
2. Copies new or changed files into an idempotent SHA256 archive on the USB stick.
3. Builds keyword and semantic indexes without modifying the source logs.
4. Exposes three local views:
   - `智能检索`: hybrid BM25 + embedding search
   - `原始日志`: direct human-readable archive browsing, copy and download
   - `光场`: a data-driven HALOFLUX visualization of the archive and index
5. Keeps raw files readable even when embedding or clustering is unavailable.

## Opening the interface (browser compatibility)

Some Chromium forks (Tabbit 1.18 and newer) enforce Local Network Access: the page
loads but every `fetch()` to the loopback address is refused. The stick therefore
ships a **portable Firefox** in `browser/` — start it with
`browser\启动记忆浏览器.cmd`, which starts the service if needed and then opens the
kit page with its own profile (no install, no LNA gating, logins travel with it).
## Quick start

Requirements:

- Windows PowerShell 5.1
- Python 3.11 when the runner creates the on-stick virtual environment
- Optional: llama.cpp binaries and local GGUF models for fully offline embeddings

Using the stick:

1. Copy this repository to the root of an NTFS USB drive.
2. Double-click `吸收日志.cmd` to discover and archive logs from the current machine.
3. Double-click `启动检索.cmd`.
4. Open <http://127.0.0.1:18200>.

The first run creates the runtime environment on the stick. The service binds to
`127.0.0.1` and is intended for local, single-user use.

## Opening the interface

Always open the service address <http://127.0.0.1:18200>. Do **not** open
`memory-kit/web/index.html` by double-clicking it: a `file://` page renders the
shell but the browser refuses every API request it makes, so the media list stays
empty and previews report "Failed to fetch". The page detects that origin and
shows a banner with the correct address.

If a browser enforces Local Network Access (for example Tabbit 1.18), the page
still loads but every `fetch()` to the loopback address is refused. The front
end detects that and retries GET requests through a same-origin hidden iframe,
whose DOM stays readable; append `?transport=iframe` to force that path.
`http://localhost:18200` and `http://[::1]:18200` work as well, because
`serve.py` binds both loopback families.

The front end also surfaces a dead service instead of staying silent: a failed
request writes the reason into the content pane and toasts it.

## Layout

```text
USB_ROOT/
├─ README.md / README.txt
├─ LICENSE / CREDITS.md / SECURITY.md
├─ 吸收日志.cmd
├─ 启动检索.cmd
├─ 启动本地AI.cmd
├─ memory-kit/
│  ├─ bin/                  collectors, chunking, indexing, HTTP and MCP services
│  ├─ config/               sanitized configuration templates
│  ├─ tests/                standard-library and service tests
│  ├─ web/                  search, raw archive and HALOFLUX views
│  ├─ corpus/               generated archive, ignored by Git
│  ├─ index/                generated chunks/vectors/community index, ignored by Git
│  ├─ runtime/              generated venv and caches, ignored by Git
│  └─ state/                sessions and runtime state, ignored by Git
├─ local-ai/
│  ├─ start-local-ai.ps1
│  ├─ 启动本地AI.cmd
│  ├─ models/               put GGUF models here, ignored by Git
│  ├─ llama/                Vulkan llama.cpp build, ignored by Git
│  └─ llama-cpu/            CPU llama.cpp build, ignored by Git
└─ 我的文件/                 personal files, ignored by Git
```

See [USB-LAYOUT.md](USB-LAYOUT.md) for the complete responsibility map.

## Configuration

- `memory-kit/config/machines.json`: maps `COMPUTERNAME` to local log roots.
- `memory-kit/config/kit.json`: embedding endpoints, chunking and clustering.
- `memory-kit/config/categories.json`: file-organizer categories.
- `memory-kit/config/secret.ps1`: never committed; optional tunnel credentials.

The first `pipeline.ps1` run can discover log roots and register the current machine.
Use `-Roots` to provide roots explicitly.

## Data and privacy

The repository deliberately excludes:

- `memory-kit/corpus/`
- `memory-kit/index/`
- `memory-kit/runtime/`
- `memory-kit/state/`
- `memory-kit/config/secret.ps1`
- local models and llama.cpp binaries
- files under `我的文件/`

Audit the repository before publishing a fork. The layout is portable; the
knowledge stored on a real stick is not.

## Credits

See [CREDITS.md](CREDITS.md). Special thanks to:

- **Ryder191 / HALOFLUX** for the full Canvas data-field renderer.
- **CJackHwang / ds2api** for the protocol-adapter and shared-core architecture that
  informed the memory gateway design.

## License

Original code in this layout is released under the MIT License. Third-party
components retain their own licenses and notices.
