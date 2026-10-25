# Credits and Attribution

## HALOFLUX

- Project: [Ryder191/haloflux](https://github.com/Ryder191/haloflux)
- Upstream commit used: `225e2b2862b3d64ae9f6e0b012b27ccbe004e3d0`
- License: MIT
- Used for: the full Canvas light-field renderer, data ring, beam layers,
  automatic camera, control console and visual language.

Our derivative keeps the upstream license at
`memory-kit/web/HALOFLUX-LICENSE.txt`. The memory-kit version replaces the original
demo data with live archive, chunk, vector and community metrics.

## ds2api

- Project: [CJackHwang/ds2api](https://github.com/CJackHwang/ds2api)
- Reference commit: `8316cf8a0352e900e03ce600b792083f590d80e2`
- License: GNU AGPL-3.0
- Used as: architectural reference only.

The memory-kit implementation borrows the ideas of protocol adapters, a normalized
request/turn model, one shared business core, bounded owner-scoped history and TTL
response caching. No ds2api source files are vendored into this repository.

## Other Open Source Components

- [llama.cpp](https://github.com/ggml-org/llama.cpp) for local inference
- Qwen3-Embedding and Qwen3 model families for optional local embeddings/chat
- `numpy`, `networkx`, `rank-bm25`, `jieba`, `requests` and the MCP Python SDK

Model files and compiled llama.cpp binaries are not distributed in this repository.
